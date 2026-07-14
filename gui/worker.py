# -*- coding: utf-8 -*-
import os
import traceback
from PySide6.QtCore import QThread, Signal

from core.bader_runner import BaderRunner
from core.parser import VaspParser
from core.calculator import ChargeCalculator

class AnalysisWorker(QThread):
    """
    Background worker thread to handle heavy VASP parsing, CHGCAR summing,
    and bader execution without freezing the GUI.
    """
    # Signals to communicate with the main GUI
    progress = Signal(str)
    finished = Signal(object, object, object) # struct, full_df, error_msg
    thread_completed = Signal()
    
    def __init__(self, ws_path, setup_config, bader_exe_path="bader.exe"):
        super().__init__()
        self.ws_path = ws_path
        self.setup_config = setup_config
        self.bader_exe_path = bader_exe_path
        
    def run(self):
        try:
            struct = None
            elements = []
            
            # 1. Look for structure
            contcar_path = os.path.join(self.ws_path, "CONTCAR")
            poscar_path = os.path.join(self.ws_path, "POSCAR")
            
            struct_path = None
            if os.path.exists(contcar_path):
                struct_path = contcar_path
                self.progress.emit("找到 CONTCAR...")
            elif os.path.exists(poscar_path):
                struct_path = poscar_path
                self.progress.emit("未找到 CONTCAR，使用 POSCAR...")
                
            if struct_path:
                struct, elements = VaspParser.parse_structure(struct_path)
            else:
                raise FileNotFoundError("未在工作区找到 CONTCAR 或 POSCAR！")
                
            # 2. Determine ZVAL Mapping
            potcar_path = os.path.join(self.ws_path, "POTCAR")
            zval_map = {}
            if os.path.exists(potcar_path):
                self.progress.emit("解析 POTCAR 读取 ZVAL...")
                dict_map, _, _ = VaspParser.parse_potcar_zval(potcar_path)
                # Map dict element to all atoms initially
                for i, el in enumerate(elements, 1):
                    zval_map[i] = dict_map.get(el, 0)
                    
            # Override with manual config
            zval_config = self.setup_config.get("zval", "")
            manual_zval_str = ""
            if isinstance(zval_config, dict):
                if zval_config.get("mode") == "manual":
                    manual_zval_str = zval_config.get("manual_str", "")
            else:
                manual_zval_str = zval_config # fallback
                
            if manual_zval_str:
                self.progress.emit("应用手动 ZVAL 覆盖规则...")
                manual_map = ChargeCalculator.parse_zval_input(manual_zval_str, len(elements), elements)
                zval_map.update(manual_map) # Overwrite
                
            if not zval_map:
                raise ValueError("未找到 POTCAR 且未手动输入 ZVAL，无法计算净电荷！")

            # 3. Check for ACF.dat or run Bader
            acf_path = os.path.join(self.ws_path, "ACF.dat")
            
            if not os.path.exists(acf_path):
                self.progress.emit("未找到 ACF.dat，准备运行 bader...")
                
                chgcar_path = os.path.join(self.ws_path, "CHGCAR")
                if not os.path.exists(chgcar_path):
                    raise FileNotFoundError("缺失 CHGCAR，无法运行 Bader 分析！")
                    
                runner = BaderRunner(self.bader_exe_path)
                if not runner.check_bader_exists():
                    raise FileNotFoundError(f"未找到可执行文件: {self.bader_exe_path}，请在设置中指定正确路径。")
                    
                # Optional: Sum AECCAR if exist
                aeccar0 = os.path.join(self.ws_path, "AECCAR0")
                aeccar2 = os.path.join(self.ws_path, "AECCAR2")
                ref_path = None
                
                if os.path.exists(aeccar0) and os.path.exists(aeccar2):
                    self.progress.emit("发现 AECCAR0 和 AECCAR2，执行网格相加 (CHGCAR_sum)...")
                    ref_path = BaderRunner.sum_chgcar(self.ws_path, aeccar0, aeccar2)
                    
                self.progress.emit("正在执行 bader 计算 (可能需要几分钟，请耐心等待)...")
                success, output = runner.run_bader(self.ws_path, chgcar_path, ref_path)
                
                if not success:
                    raise RuntimeError(f"Bader 执行失败:\n{output}")
                    
                if not os.path.exists(acf_path):
                    raise FileNotFoundError("Bader 运行结束，但未生成 ACF.dat！")

            # 4. Parse ACF and Calculate Net Charges
            self.progress.emit("解析 ACF.dat ...")
            acf_df = VaspParser.parse_acf(acf_path)
            
            self.progress.emit("计算净电荷...")
            full_df = ChargeCalculator.calculate_net_charges(acf_df, zval_map, elements)
            
            self.progress.emit("分析完成！")
            self.finished.emit(struct, full_df, None)
            
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(None, None, str(e))
        finally:
            self.thread_completed.emit()
