import subprocess
import os
import shutil

class BaderRunner:
    """Handles the execution of the bader command line tool."""
    
    def __init__(self, bader_executable_path="bader.exe"):
        self.bader_exe = bader_executable_path

    def check_bader_exists(self):
        # Check if the executable is in path or exists at the specified path
        if os.path.exists(self.bader_exe):
            return True
        return shutil.which(self.bader_exe) is not None

    def run_bader(self, working_dir, chgcar_path, ref_path=None):
        """
        Runs bader.exe inside the working directory.
        If ref_path is provided, runs: bader CHGCAR -ref CHGCAR_sum
        Else runs: bader CHGCAR
        """
        if not self.check_bader_exists():
            raise FileNotFoundError(f"bader executable not found: {self.bader_exe}")
            
        cmd = [self.bader_exe, chgcar_path]
        if ref_path:
            cmd.extend(["-ref", ref_path])
            
        try:
            # Using Popen to capture stdout/stderr for progress could be done later.
            # For now, we wait for it to complete.
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
            
    @staticmethod
    def sum_chgcar(working_dir, aeccar0_path, aeccar2_path, output_name="CHGCAR_sum"):
        """
        Sums AECCAR0 and AECCAR2 to create CHGCAR_sum using numpy for speed.
        (Python equivalent of chgsum.pl)
        """
        import numpy as np
        
        with open(aeccar0_path, 'r') as f0, open(aeccar2_path, 'r') as f2:
            lines0 = f0.readlines()
            lines2 = f2.readlines()
            
        if len(lines0) != len(lines2):
            raise ValueError("AECCAR0 and AECCAR2 have different number of lines!")
            
        out_lines = []
        # Find where data starts (usually after the blank line following coordinates)
        # CHGCAR format has atoms, then empty line, then grid size, then data.
        grid_line_idx = -1
        for i, line in enumerate(lines0):
            out_lines.append(line) # Temporarily append everything
            parts = line.split()
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                grid_line_idx = i
                break
                
        if grid_line_idx == -1:
            raise ValueError("Could not find grid size line in AECCAR0")
            
        # Write up to grid size
        out_lines = lines0[:grid_line_idx+1]
        
        # Now process grid data
        data_start = grid_line_idx + 1
        
        # Read the rest of the lines
        # This is a bit memory intensive but safe for typical VASP files on modern PCs
        # For huge files, chunking would be better.
        for i in range(data_start, len(lines0)):
            # Augmentation occupancies might exist at the end, so we handle it generically
            line0 = lines0[i]
            line2 = lines2[i]
            
            if "augmentation" in line0:
                # Reached augmentation occupancies, just copy the rest from aeccar0 or break
                out_lines.extend(lines0[i:])
                break
                
            vals0 = np.array([float(x) for x in line0.split()])
            vals2 = np.array([float(x) for x in line2.split()])
            
            if len(vals0) > 0 and len(vals0) == len(vals2):
                sum_vals = vals0 + vals2
                # Format exactly as VASP (e.g., 5E11)
                fmt_line = "".join([f" {val:18.11E}" for val in sum_vals]) + "\n"
                out_lines.append(fmt_line)
            else:
                out_lines.append(line0) # Keep original if mismatch or empty
                
        out_path = os.path.join(working_dir, output_name)
        with open(out_path, 'w') as f:
            f.writelines(out_lines)
            
        return out_path

