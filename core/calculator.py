# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

from core.selection import SelectionError, SelectionResolver


TargetSelectionError = SelectionError


class ChargeCalculator:
    """Handles the computation of Net Charges and Custom Segment Summation."""
    
    @staticmethod
    def parse_zval_input(zval_str, total_atoms, elements):
        """
        Parses a user-provided ZVAL configuration string and returns a dictionary 
        mapping atom_index (1-based) to its ZVAL.
        
        Example zval_str format:
        O: 6
        Fe: 8
        1-5: 8
        6-10: 14
        
        Args:
            zval_str (str): The configuration text.
            total_atoms (int): Total number of atoms.
            elements (list): List of element symbols for each atom (1-based index mapping: elements[i-1]).
            
        Returns:
            dict: {atom_idx (int): zval (float)}
        """
        zval_map = {}
        
        # Parse line by line
        for line in zval_str.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
                
            key_part, val_part = line.split(':', 1)
            key_part = key_part.strip()
            val_part = val_part.strip()
            
            try:
                zval_val = float(val_part)
            except ValueError:
                continue # Ignore malformed values
                
            # Check if key is a range like "1-5" or "10"
            if re.match(r'^\d+(-\d+)?$', key_part):
                if '-' in key_part:
                    start, end = map(int, key_part.split('-'))
                    for i in range(start, end + 1):
                        zval_map[i] = zval_val
                else:
                    zval_map[int(key_part)] = zval_val
            else:
                # Treat as element symbol
                target_element = key_part
                for i, el in enumerate(elements, start=1):
                    # Only assign if it hasn't been specifically assigned by index
                    if el == target_element and i not in zval_map:
                        zval_map[i] = zval_val
                        
        return zval_map

    @staticmethod
    def calculate_net_charges(acf_df, zval_map, elements):
        """
        Calculates Net Charge = ZVAL - Bader_Charge for all atoms.
        
        Args:
            acf_df (pd.DataFrame): DataFrame containing 'Atom' and 'Bader_Charge'.
            zval_map (dict): {atom_idx: zval}
            elements (list): Element symbols.
            
        Returns:
            pd.DataFrame: A new DataFrame with Elements, ZVAL, and Net_Charge appended.
        """
        df = acf_df.copy()
        
        # Add Element column
        df['Element'] = [elements[int(idx)-1] if int(idx)-1 < len(elements) else "X" for idx in df['Atom']]
        
        # Add ZVAL column
        df['ZVAL'] = df['Atom'].map(zval_map)
        
        # Calculate Bader Charge (电子净转移)
        # 根据用户要求：得电子为正，失电子为负
        df['Bader_Charge'] = df['CHARGE'] - df['ZVAL']
        
        return df

    @staticmethod
    def parse_target_atoms(target_str, total_atoms, elements):
        """
        Parses a target string (e.g., "1-5, 8", "O, Fe") into a list of atom indices to keep.
        """
        return list(SelectionResolver.resolve(target_str, elements, total_atoms))

    @staticmethod
    def calculate_custom_sum(df, target_str, elements):
        """
        Calculates the sum of net charges for a custom target string.
        Returns the sum and the list of atom indices involved.
        """
        total_atoms = len(elements)
        target_indices = ChargeCalculator.parse_target_atoms(target_str, total_atoms, elements)
        
        filtered_df = df[df['Atom'].isin(target_indices)]
        total_charge = filtered_df['Bader_Charge'].sum()
        
        return total_charge, target_indices

    @staticmethod
    def aggregate_charge(df, expression=""):
        """Return one consistent statistics payload for an atom selection."""
        if df is None or df.empty:
            raise TargetSelectionError("没有可用于统计的原子数据")
        elements = df.sort_values("Atom")["Element"].astype(str).tolist()
        total_atoms = int(df["Atom"].max())
        indices = ChargeCalculator.parse_target_atoms(expression, total_atoms, elements)
        selected = df[df["Atom"].isin(indices)]["Bader_Charge"].astype(float)
        if selected.empty:
            raise TargetSelectionError(f"表达式未匹配任何原子: {expression}")
        return {
            "expression": expression or "",
            "atom_indices": sorted(int(value) for value in df[df["Atom"].isin(indices)]["Atom"]),
            "count": int(selected.count()),
            "sum": float(selected.sum()),
            "mean": float(selected.mean()),
            "std": float(selected.std()) if len(selected) > 1 else 0.0,
            "max": float(selected.max()),
            "min": float(selected.min()),
        }

    @staticmethod
    def aggregate_by_element(df, metric="sum"):
        """Aggregate Bader charge transfer by element using sum or mean."""
        if metric not in {"sum", "mean"}:
            raise ValueError("元素聚合方式必须为 sum 或 mean")
        if df is None or df.empty:
            return {}
        grouped = df.groupby("Element")["Bader_Charge"]
        values = grouped.sum() if metric == "sum" else grouped.mean()
        return {str(element): float(value) for element, value in values.items()}

    @staticmethod
    def prepare_plot_data(data_dict, level="atom", metric="sum", fragments=None, target=""):
        """Build plot-ready DataFrames at atom, fragment, or element level."""
        prepared = {}
        fragments = fragments or {}
        for workspace, payload in (data_dict or {}).items():
            df = payload.get("df")
            if df is None:
                continue
            if level == "atom":
                plot_df = df.copy()
                if target.strip() and not plot_df.empty:
                    elements = plot_df.sort_values("Atom")["Element"].astype(str).tolist()
                    indices = ChargeCalculator.parse_target_atoms(
                        target, int(plot_df["Atom"].max()), elements
                    )
                    plot_df = plot_df[plot_df["Atom"].isin(indices)].copy()
            elif level == "element":
                grouped = df.groupby("Element")["Bader_Charge"]
                values = grouped.sum() if metric == "sum" else grouped.mean()
                plot_df = pd.DataFrame({
                    "Atom": values.index.astype(str),
                    "Element": values.index.astype(str),
                    "Bader_Charge": values.values.astype(float),
                })
            elif level == "fragment":
                rows = []
                for name, expression in fragments.get(workspace, {}).items():
                    stats = ChargeCalculator.aggregate_charge(df, expression)
                    rows.append({
                        "Atom": str(name),
                        "Element": "Fragment",
                        "Bader_Charge": stats["sum"],
                    })
                plot_df = pd.DataFrame(
                    rows, columns=["Atom", "Element", "Bader_Charge"]
                )
            else:
                raise ValueError(f"未知绘图层级: {level}")
            prepared[workspace] = {"df": plot_df, "struct": payload.get("struct")}
        return prepared
