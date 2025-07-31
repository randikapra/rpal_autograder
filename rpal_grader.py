#!/usr/bin/env python3
"""
Enhanced RPAL Assignment Automated Grading System - Modified for Strict Requirements
Handles subfolder search, strict scoring, and better error handling
Updated to match specific evaluation requirements
"""

import os
import subprocess
import csv
import sys
import shlex
from pathlib import Path
import difflib
from typing import Dict, List, Tuple, Optional
import re
import traceback

class RPALGrader:
    def __init__(self, workspace_path: str, rpal_executable: str = "./rpal/rpal.exe"):
        """
        Initialize the RPAL grader
        
        Args:
            workspace_path: Path to grading_workspace
            rpal_executable: Path to RPAL interpreter executable
        """
        self.workspace_path = Path(workspace_path)
        self.rpal_path = Path(rpal_executable)
        self.submissions_path = self.workspace_path / "submissions"
        self.test_cases_path = self.workspace_path / "test_cases"
        
        # Test cases mapping: input file -> (expected output, expected AST output)
        self.test_cases = {
            "t9input.txt": ("t9inputfinaloutput.txt", "t9inputast.txt"),
            "t2input.txt": ("t2inputfinaloutput.txt", "t2inputast.txt"),
            "wsum1input.txt": ("wsum1inputfinaloutput.txt", "wsum1inputast.txt"),
            "vectorsumintput.txt": ("vectorsumintputfinaloutput.txt", "vectorsumintputast.txt"),
            "towersinput.txt": ("towerfinaloutput.txt", "towerast.txt")
        }
        
        # Scoring per test case: 14 points total, 14/3 ≈ 4.67 per mode
        self.points_per_mode = 14.0 / 3.0  # 4.67 points per mode (run/ast/st)
        
        # Results storage
        self.results = []
        
    def find_files_recursively(self, submission_folder: Path, patterns: List[str]) -> List[Path]:
        """
        Find files matching patterns recursively in submission folder and subfolders
        """
        found_files = []
        
        def search_directory(directory: Path, depth: int = 0):
            if depth > 3:  # Limit recursion depth to avoid infinite loops
                return
                
            try:
                for item in directory.iterdir():
                    if item.is_file():
                        for pattern in patterns:
                            if item.name.lower() == pattern.lower() or item.match(pattern):
                                found_files.append(item)
                    elif item.is_dir() and not item.name.startswith('.'):
                        search_directory(item, depth + 1)
            except (PermissionError, OSError):
                pass
        
        search_directory(submission_folder)
        return found_files
    
    def find_makefile(self, submission_folder: Path) -> Optional[Path]:
        """
        Find Makefile in submission folder and subfolders (case insensitive)
        """
        makefiles = self.find_files_recursively(submission_folder, ['Makefile', 'makefile', 'Makefile.txt', 'makefile.txt'])
        return makefiles[0] if makefiles else None
    
    def find_program_file(self, submission_folder: Path) -> Optional[Path]:
        """
        Find the main program file in submission folder and subfolders
        Priority: myrpal.py > *.py > *.rpal > *.java > *.cpp > *.c > others
        """
        # Look for myrpal.py first (highest priority)
        myrpal_files = self.find_files_recursively(submission_folder, ['myrpal.py'])
        if myrpal_files:
            return myrpal_files[0]
        
        # Look for other Python files
        py_files = self.find_files_recursively(submission_folder, ['*.py'])
        if py_files:
            return py_files[0]
            
        # Look for .rpal files
        rpal_files = self.find_files_recursively(submission_folder, ['*.rpal'])
        if rpal_files:
            return rpal_files[0]
            
        # Look for Java files (main class)
        java_files = self.find_files_recursively(submission_folder, ['*.java'])
        for java_file in java_files:
            if 'main' in java_file.name.lower():
                return java_file
        if java_files:
            return java_files[0]
        
        # Look for C++ files
        cpp_files = self.find_files_recursively(submission_folder, ['*.cpp', '*.cxx', '*.cc'])
        if cpp_files:
            return cpp_files[0]
            
        # Look for C files
        c_files = self.find_files_recursively(submission_folder, ['*.c'])
        if c_files:
            return c_files[0]
            
        # Look for executable files
        for item in submission_folder.rglob('*'):
            if item.is_file() and os.access(item, os.X_OK) and '.' not in item.name:
                return item
                
        return None
    
    def normalize_ast_structure(self, ast_content: str) -> str:
        """
        Normalize AST structure by converting between dots and spaces
        This handles the mismatch between expected (dots) and actual (spaces) AST formats
        """
        lines = ast_content.strip().split('\n')
        normalized_lines = []
        
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
                
            # Count leading dots or spaces
            leading_dots = len(line) - len(line.lstrip('.'))
            leading_spaces = len(line) - len(line.lstrip(' '))
            
            # Get the actual content (after dots/spaces)
            if leading_dots > 0:
                content = line.lstrip('.')
                indent_level = leading_dots
            elif leading_spaces > 0:
                content = line.lstrip(' ')
                # Assume each 2 spaces = 1 level, or each 4 spaces = 1 level
                if leading_spaces % 4 == 0:
                    indent_level = leading_spaces // 4
                elif leading_spaces % 2 == 0:
                    indent_level = leading_spaces // 2
                else:
                    indent_level = leading_spaces
            else:
                content = line
                indent_level = 0
            
            # Normalize to dots format for comparison
            normalized_line = '.' * indent_level + content
            normalized_lines.append(normalized_line)
        
        return '\n'.join(normalized_lines)
    
    def extract_core_answer(self, output: str) -> str:
        """
        Extract core answer from output, ignoring extra content
        This handles cases where student output has extra information
        """
        # Clean output first
        output = output.strip().replace('\r\n', '\n').replace('\r', '\n')
        
        # Handle IDENTIFIER vs ID variations
        output = re.sub(r'\bIDENTIFIER\b', 'ID', output)
        
        # For AST output, preserve structure
        if any(keyword in output for keyword in ['.gamma', '.lambda', '.tau', 'gamma', 'lambda', 'tau', '.+', '.>', '.=']):
            return self.normalize_ast_structure(output)
        
        # For regular output, try to extract the final answer
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        
        if not lines:
            return ""
        
        # If it's a single line, return it
        if len(lines) == 1:
            return lines[0]
        
        # Try to find lines that look like answers (numbers, simple expressions)
        answer_patterns = [
            r'^\d+$',  # Just numbers
            r'^-?\d+$',  # Negative numbers
            r'^\d+\.\d+$',  # Decimals
            r'^[a-zA-Z_][a-zA-Z0-9_]*$',  # Simple identifiers
            r'^[()]+$',  # Parentheses
            r'^[a-zA-Z0-9\s\(\)]+$',  # Simple expressions
        ]
        
        potential_answers = []
        for line in lines:
            for pattern in answer_patterns:
                if re.match(pattern, line):
                    potential_answers.append(line)
                    break
        
        # Return the last potential answer, or the last line if no patterns match
        if potential_answers:
            return potential_answers[-1]
        else:
            return lines[-1]
    
    def compare_outputs_strict(self, actual: str, expected: str, is_ast: bool = False) -> Tuple[bool, float]:
        """
        Strict comparison for exact matching with partial credit based on similarity
        Returns: (is_perfect_match, similarity_score)
        """
        print(f"    DEBUG - Actual output: '{actual.strip()}'")
        print(f"    DEBUG - Expected output: '{expected.strip()}'") 
        if is_ast:
            actual_normalized = self.normalize_ast_structure(actual)
            expected_normalized = self.normalize_ast_structure(expected)
        else:
            actual_normalized = self.extract_core_answer(actual)
            expected_normalized = self.extract_core_answer(expected)
        
        # Check for exact match first
        if actual_normalized == expected_normalized:
            return True, 1.0
        
        # Try with IDENTIFIER <-> ID conversion
        actual_id = re.sub(r'\bIDENTIFIER\b', 'ID', actual_normalized)
        expected_id = re.sub(r'\bIDENTIFIER\b', 'ID', expected_normalized)
        
        if actual_id == expected_id:
            return True, 1.0
            
        actual_identifier = re.sub(r'\bID\b', 'IDENTIFIER', actual_normalized)
        expected_identifier = re.sub(r'\bID\b', 'IDENTIFIER', expected_normalized)
        
        if actual_identifier == expected_identifier:
            return True, 1.0
        
        # Calculate similarity for partial credit
        if not expected_normalized or not actual_normalized:
            return False, 0.0
        
        if is_ast:
            # For AST, use line-by-line comparison
            actual_lines = actual_normalized.split('\n')
            expected_lines = expected_normalized.split('\n')
            
            if len(actual_lines) == 0 or len(expected_lines) == 0:
                return False, 0.0
            
            correct_lines = 0
            max_lines = max(len(actual_lines), len(expected_lines))
            
            for i in range(min(len(actual_lines), len(expected_lines))):
                if actual_lines[i].strip() == expected_lines[i].strip():
                    correct_lines += 1
                else:
                    # Partial credit for similar structure
                    actual_tokens = actual_lines[i].strip().replace('.', '').strip()
                    expected_tokens = expected_lines[i].strip().replace('.', '').strip()
                    if actual_tokens == expected_tokens:
                        correct_lines += 0.7  # Partial credit for correct content, wrong indentation
            
            similarity = correct_lines / max_lines
        else:
            # Use character-level similarity for regular output
            similarity = difflib.SequenceMatcher(None, actual_normalized, expected_normalized).ratio()
        
        return False, max(0.0, similarity)
    
    def parse_makefile(self, makefile_path: Path) -> Dict[str, str]:
        """
        Parse Makefile to extract run commands - ROBUST VERSION
        Handles various student formatting styles
        """
        commands = {}
        
        try:
            with open(makefile_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            current_target = None
            
            for line in lines:
                line = line.rstrip('\n\r')
                
                # Skip empty lines and comments
                if not line.strip() or line.strip().startswith('#'):
                    continue
                
                # Check if this is a target line (run:, ast:, st:)
                target_match = re.match(r'^(run|ast|st)\s*:\s*(.*)$', line.strip())
                if target_match:
                    target = target_match.group(1)
                    command_part = target_match.group(2).strip()
                    
                    if command_part:  # Command on same line
                        commands[target] = command_part
                    else:  # Command on next line(s)
                        current_target = target
                    continue
                
                # If we're looking for command for current target
                if current_target and line.startswith(('\t', '    ', ' ')):
                    command = line.strip()
                    if command and not command.startswith('#'):
                        commands[current_target] = command
                        current_target = None  # Found the command
                    continue
                
                # Reset if we hit a new section
                if line and not line.startswith((' ', '\t')):
                    current_target = None
            
            print(f"    DEBUG - Parsed Makefile commands: {commands}")
                        
        except Exception as e:
            print(f"    Error parsing Makefile: {e}")
            
        return commands

    def run_with_makefile(self, submission_folder: Path, makefile_commands: Dict[str, str], 
                        input_file: Path, mode: str = "run") -> Tuple[str, str, int]:
        """
        Run program using Makefile commands - HANDLES ALL VARIABLE FORMATS
        """
        try:
            if mode not in makefile_commands:
                return "", f"No {mode} target found in Makefile", -1

            command = makefile_commands[mode]
            original_command = command
            
            # Get absolute input file path
            input_file_abs = str(input_file.absolute())
            input_file_rel = str(input_file)
            input_file_name = input_file.name
            
            # Handle ALL possible variable formats students might use
            variable_replacements = [
                ('$(file)', input_file_abs),
                ('$file', input_file_abs), 
                ('${file}', input_file_abs),
                ('$(FILE)', input_file_abs),
                ('$FILE', input_file_abs),
                ('${FILE}', input_file_abs),
                ('$(input)', input_file_abs),
                ('$input', input_file_abs),
                ('${input}', input_file_abs),
                ('$(INPUT)', input_file_abs),
                ('$INPUT', input_file_abs),
                ('${INPUT}', input_file_abs),
                ('$(filename)', input_file_abs),
                ('$filename', input_file_abs),
                ('${filename}', input_file_abs),
                ('$(FILENAME)', input_file_abs),
                ('$FILENAME', input_file_abs),
                ('${FILENAME}', input_file_abs),
                # Python variables
                ('$(PYTHON)', 'python3'),
                ('$PYTHON', 'python3'),
                ('${PYTHON}', 'python3'),
                ('$(python)', 'python3'),
                ('$python', 'python3'),
                ('${python}', 'python3'),
                ('$(PY)', 'python3'),
                ('$PY', 'python3'),
                ('${PY}', 'python3'),
            ]
            
            # Apply replacements
            for old, new in variable_replacements:
                command = command.replace(old, new)
            
            # Handle cases where students hardcode filename patterns
            # Look for common patterns and replace if input file not already in command
            if input_file_abs not in command and input_file_rel not in command:
                # Try to find and replace common hardcoded patterns
                patterns_to_replace = [
                    r'\b\w*input\w*\.txt\b',  # anyinput.txt, input.txt, testinput.txt
                    r'\b\w*test\w*\.txt\b',   # test.txt, test1.txt, etc.
                    r'\b\w*\.rpal\b',         # any .rpal file
                ]
                
                replaced = False
                for pattern in patterns_to_replace:
                    if re.search(pattern, command, re.IGNORECASE):
                        command = re.sub(pattern, input_file_abs, command, flags=re.IGNORECASE)
                        replaced = True
                        break
                
                # If still no input file in command, append it
                if not replaced:
                    command = f"{command} {input_file_abs}"
            
            print(f"    DEBUG - Original command: {original_command}")
            print(f"    DEBUG - Processed command: {command}")
            
            # Get the makefile directory for proper execution context
            makefile_dir = Path(makefile_commands.get('_makefile_dir', submission_folder))
            
            result = subprocess.run(
                command, 
                shell=True,
                capture_output=True, 
                text=True, 
                timeout=30,
                cwd=makefile_dir,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f"    DEBUG - Return code: {result.returncode}")
            print(f"    DEBUG - Stdout length: {len(result.stdout)} chars")
            print(f"    DEBUG - Stderr: '{result.stderr.strip()}'")
            if result.stdout.strip():
                print(f"    DEBUG - First 200 chars of stdout: '{result.stdout[:200]}...'")
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Program execution exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Error: {str(e)}", -1

    def try_alternative_makefile_execution(self, submission_folder: Path, makefile_path: Path, 
                                        input_file: Path, mode: str) -> Tuple[str, str, int]:
        """
        Alternative approach: Use 'make' command directly
        This handles complex Makefiles better than parsing
        """
        try:
            # Change to makefile directory
            makefile_dir = makefile_path.parent
            
            # Set environment variables that might be used in Makefile
            env = os.environ.copy()
            env['file'] = str(input_file.absolute())
            env['FILE'] = str(input_file.absolute())
            env['input'] = str(input_file.absolute())
            env['INPUT'] = str(input_file.absolute())
            env['filename'] = str(input_file.absolute())
            env['FILENAME'] = str(input_file.absolute())
            env['PYTHON'] = 'python3'
            env['python'] = 'python3'
            
            # Try using make command directly
            result = subprocess.run(
                ['make', mode, f'file={input_file.absolute()}'],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=makefile_dir,
                env=env,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f"    DEBUG - Make command result: RC={result.returncode}")
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Make command exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Make command error: {str(e)}", -1


    def run_direct_python(self, program_file: Path, input_file: Path, mode: str = "run") -> Tuple[str, str, int]:
        try:
            cmd = ['python3', str(program_file), str(input_file)]  # Put input file BEFORE flags
            
            # Add appropriate flags based on mode AFTER the input file
            if mode == "ast":
                cmd.append('-ast')
            elif mode == "st":
                cmd.append('-st')
            
            # Remove this line: cmd.append(str(input_file))  # This was adding input file twice
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Program execution exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Error: {str(e)}", -1
    
    def run_java_program(self, submission_folder: Path, program_file: Path, input_file: Path, mode: str = "run") -> Tuple[str, str, int]:
        """
        Run Java program
        """
        try:
            # Try to compile first
            compile_result = subprocess.run(
                ['javac', str(program_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            if compile_result.returncode != 0:
                return "", f"Compilation error: {compile_result.stderr}", -1
            
            # Run the program
            main_class = program_file.stem
            cmd = ['java', main_class]
            
            if mode == "ast":
                cmd.append('-ast')
            elif mode == "st":
                cmd.append('-st')
            
            cmd.append(str(input_file))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Program execution exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Error: {str(e)}", -1
    
    def run_cpp_program(self, submission_folder: Path, program_file: Path, input_file: Path, mode: str = "run") -> Tuple[str, str, int]:
        """
        Run C++ program
        """
        try:
            # Compile first
            exe_file = program_file.parent / program_file.stem
            compile_result = subprocess.run(
                ['g++', str(program_file), '-o', str(exe_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            if compile_result.returncode != 0:
                return "", f"Compilation error: {compile_result.stderr}", -1
            
            # Run the program
            cmd = [str(exe_file)]
            
            if mode == "ast":
                cmd.append('-ast')
            elif mode == "st":
                cmd.append('-st')
            
            cmd.append(str(input_file))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Program execution exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Error: {str(e)}", -1
    
    def run_c_program(self, submission_folder: Path, program_file: Path, input_file: Path, mode: str = "run") -> Tuple[str, str, int]:
        """
        Run C program
        """
        try:
            # Compile first
            exe_file = program_file.parent / program_file.stem
            compile_result = subprocess.run(
                ['gcc', str(program_file), '-o', str(exe_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            if compile_result.returncode != 0:
                return "", f"Compilation error: {compile_result.stderr}", -1
            
            # Run the program
            cmd = [str(exe_file)]
            
            if mode == "ast":
                cmd.append('-ast')
            elif mode == "st":
                cmd.append('-st')
            
            cmd.append(str(input_file))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=program_file.parent,
                encoding='utf-8',
                errors='ignore'
            )
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            return "", "Timeout: Program execution exceeded 30 seconds", -1
        except Exception as e:
            return "", f"Error: {str(e)}", -1
    
    def is_runtime_error(self, stderr: str, return_code: int) -> bool:
        """
        Check if the error is a runtime/traceback error that should get 0 marks
        """
        if return_code != 0:
            return True
        
        error_indicators = [
            'Traceback',
            'Exception',
            'Error:',
            'exception',
            'error:',
            'runtime error',
            'compilation error',
            'segmentation fault',
            'core dumped'
        ]
        
        stderr_lower = stderr.lower()
        return any(indicator in stderr_lower for indicator in error_indicators)
    
    def execute_program(self, submission_folder: Path, makefile_commands: Dict[str, str], 
                    program_file: Path, input_path: Path, mode: str) -> Tuple[str, str, int]:
        """
        Execute program with multiple fallback strategies
        """
        # Strategy 1: Try parsed Makefile commands
        if makefile_commands and mode in makefile_commands:
            stdout, stderr, returncode = self.run_with_makefile(submission_folder, makefile_commands, input_path, mode)
            
            # If successful or has meaningful output, return it
            if returncode == 0 or stdout.strip():
                return stdout, stderr, returncode
            
            print(f"    DEBUG - Makefile parsing failed, trying direct make command")
            
            # Strategy 2: Try direct make command
            makefile_path = Path(makefile_commands.get('_makefile_path', ''))
            if makefile_path and makefile_path.exists():
                stdout2, stderr2, returncode2 = self.try_alternative_makefile_execution(
                    submission_folder, makefile_path, input_path, mode)
                
                if returncode2 == 0 or stdout2.strip():
                    return stdout2, stderr2, returncode2
            
            print(f"    DEBUG - Both makefile strategies failed, falling back to direct execution")
        
        # Strategy 3: Direct execution fallback
        if program_file.suffix == '.py':
            return self.run_direct_python(program_file, input_path, mode)
        elif program_file.suffix == '.java':
            return self.run_java_program(submission_folder, program_file, input_path, mode)
        elif program_file.suffix in ['.cpp', '.cxx', '.cc']:
            return self.run_cpp_program(submission_folder, program_file, input_path, mode)
        elif program_file.suffix == '.c':
            return self.run_c_program(submission_folder, program_file, input_path, mode)
        else:
            # Try to execute as is (for compiled executables)
            try:
                cmd = [str(program_file)]
                
                if mode == "ast":
                    cmd.append('-ast')
                elif mode == "st":
                    cmd.append('-st')
                
                cmd.append(str(input_path))
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=program_file.parent,
                    encoding='utf-8',
                    errors='ignore'
                )
                
                return result.stdout, result.stderr, result.returncode
                
            except Exception as e:
                return "", f"Unsupported file type or execution error: {str(e)}", -1

    
    def grade_submission(self, submission_folder: Path) -> Dict:
        """
        Grade a single submission with strict scoring requirements
        """
        result = {
            'submission': submission_folder.name,
            'algorithm_score': 0,
            'comments_score': 0,
            'report_score': 0,
            'total_score': 0,
            'max_algorithm_score': 70,
            'test_results': {},
            'notes': [],
            'has_makefile': 'No',
            'has_program_file': 'No',
            'execution_method': 'None',
            'makefile_location': '',
            'program_file_location': '',
            'error_details': {}
        }
        
        print(f"Grading {submission_folder.name}...")
        
        # Check for Makefile (including subfolders)
        makefile_path = self.find_makefile(submission_folder)
        makefile_commands = {}
        
        if makefile_path:
            result['has_makefile'] = 'Yes'
            result['makefile_location'] = str(makefile_path.relative_to(submission_folder))
            makefile_commands = self.parse_makefile(makefile_path)
            makefile_commands['_makefile_dir'] = str(makefile_path.parent)
            makefile_commands['_makefile_path'] = str(makefile_path)  # ADD THIS LINE
            result['execution_method'] = 'Makefile'
            print(f"  Found Makefile at: {makefile_path.relative_to(submission_folder)}")
            print(f"  Makefile commands: {list(k for k in makefile_commands.keys() if not k.startswith('_'))}")
        
        # Find program file (including subfolders)
        program_file = self.find_program_file(submission_folder)
        
        if program_file:
            result['has_program_file'] = 'Yes'
            result['program_file_location'] = str(program_file.relative_to(submission_folder))
            print(f"  Found program file: {program_file.relative_to(submission_folder)}")
        else:
            result['notes'].append("No program file found in folder or subfolders")
            print(f"  No program file found")
            return result
        
        # Determine execution method if not using Makefile
        if not makefile_path:
            if program_file.suffix == '.py':
                result['execution_method'] = 'Direct Python'
            elif program_file.suffix == '.java':
                result['execution_method'] = 'Direct Java'
            elif program_file.suffix in ['.cpp', '.cxx', '.cc']:
                result['execution_method'] = 'Direct C++'
            elif program_file.suffix == '.c':
                result['execution_method'] = 'Direct C'
            else:
                result['execution_method'] = 'Direct Execution'
        
        # Test each test case with strict scoring
        total_test_score = 0
        
        for input_file, (expected_output_file, expected_ast_file) in self.test_cases.items():
            test_name = input_file.replace("input.txt", "").replace(".txt", "")
            input_path = self.test_cases_path / input_file
            expected_output_path = self.test_cases_path / expected_output_file
            expected_ast_path = self.test_cases_path / expected_ast_file
            
            if not input_path.exists():
                print(f"    {test_name}: Input file not found - SKIPPING")
                result['test_results'][test_name] = {
                    'run_score': 0,
                    'ast_score': 0,
                    'st_score': 0,
                    'total': 0,
                    'errors': {'run': 'Input file missing', 'ast': 'Input file missing', 'st': 'Input file missing'}
                }
                continue
            
            mode_scores = {'run': 0, 'ast': 0, 'st': 0}
            test_errors = {'run': '', 'ast': '', 'st': ''}
            
            print(f"    {test_name}:", end=" ")
            
            # Test 1: Normal execution (run mode)
            try:
                actual_output, stderr, return_code = self.execute_program(
                    submission_folder, makefile_commands, program_file, input_path, "run"
                )
                
                if self.is_runtime_error(stderr, return_code):
                    mode_scores['run'] = 0
                    test_errors['run'] = f"Runtime error (RC:{return_code})"
                    print("RUN:0", end=" ")
                elif expected_output_path.exists() and actual_output.strip():
                    with open(expected_output_path, 'r', encoding='utf-8', errors='ignore') as f:
                        expected_output = f.read()
                    
                    is_perfect, similarity = self.compare_outputs_strict(actual_output, expected_output, is_ast=False)
                    
                    if is_perfect:
                        mode_scores['run'] = self.points_per_mode
                        print(f"RUN:{self.points_per_mode:.1f}", end=" ")
                    else:
                        mode_scores['run'] = similarity * self.points_per_mode
                        test_errors['run'] = f"Partial match (similarity: {similarity:.2f})"
                        print(f"RUN:{mode_scores['run']:.1f}", end=" ")
                else:
                    mode_scores['run'] = 0
                    test_errors['run'] = "No output or missing expected file"
                    print("RUN:0", end=" ")
            except Exception as e:
                mode_scores['run'] = 0
                test_errors['run'] = f"Execution error: {str(e)}"
                print("RUN:0", end=" ")
            
            # Test 2: AST execution
            try:
                actual_ast_output, stderr_ast, return_code_ast = self.execute_program(
                    submission_folder, makefile_commands, program_file, input_path, "ast"
                )
                
                if self.is_runtime_error(stderr_ast, return_code_ast):
                    mode_scores['ast'] = 0
                    test_errors['ast'] = f"Runtime error (RC:{return_code_ast})"
                    print("AST:0", end=" ")
                elif expected_ast_path.exists() and actual_ast_output.strip():
                    with open(expected_ast_path, 'r', encoding='utf-8', errors='ignore') as f:
                        expected_ast_output = f.read()
                    
                    is_perfect, similarity = self.compare_outputs_strict(actual_ast_output, expected_ast_output, is_ast=True)
                    
                    if is_perfect:
                        mode_scores['ast'] = self.points_per_mode
                        print(f"AST:{self.points_per_mode:.1f}", end=" ")
                    else:
                        mode_scores['ast'] = similarity * self.points_per_mode
                        test_errors['ast'] = f"Partial match (similarity: {similarity:.2f})"
                        print(f"AST:{mode_scores['ast']:.1f}", end=" ")
                else:
                    mode_scores['ast'] = 0
                    test_errors['ast'] = "No output or missing expected file"
                    print("AST:0", end=" ")
            except Exception as e:
                mode_scores['ast'] = 0
                test_errors['ast'] = f"Execution error: {str(e)}"
                print("AST:0", end=" ")
            
            # Test 3: ST execution
            # try:
            #     actual_st_output, stderr_st, return_code_st = self.execute_program(
            #         submission_folder, makefile_commands, program_file, input_path, "st"
            #     )
                
            #     if self.is_runtime_error(stderr_st, return_code_st):
            #         mode_scores['st'] = 0
            #         test_errors['st'] = f"Runtime error (RC:{return_code_st})"
            #         print("ST:0")
            #     elif expected_ast_path.exists() and actual_st_output.strip():
            #         with open(expected_ast_path, 'r', encoding='utf-8', errors='ignore') as f:
            #             expected_st_output = f.read()
                    
            #         is_perfect, similarity = self.compare_outputs_strict(actual_st_output, expected_st_output, is_ast=True)
                    
            #         if is_perfect:
            #             mode_scores['st'] = self.points_per_mode
            #             print(f"ST:{self.points_per_mode:.1f}")
            #         else:
            #             mode_scores['st'] = similarity * self.points_per_mode
            #             test_errors['st'] = f"Partial match (similarity: {similarity:.2f})"
            #             print(f"ST:{mode_scores['st']:.1f}")
            #     else:
            #         mode_scores['st'] = 0
            #         test_errors['st'] = "No output or missing expected file"
            #         print("ST:0")
            # except Exception as e:
            #     mode_scores['st'] = 0
            #     test_errors['st'] = f"Execution error: {str(e)}"
            #     print("ST:0")
            # ST grading - simplified since it's same as AST
            mode_scores['st'] = mode_scores['ast']  # Copy AST score
            test_errors['st'] = test_errors.get('ast', '')
            print(f"ST:{mode_scores['st']:.1f}")
            test_score = sum(mode_scores.values())
            
            result['test_results'][test_name] = {
                'run_score': round(mode_scores['run'], 2),
                'ast_score': round(mode_scores['ast'], 2),
                'st_score': round(mode_scores['st'], 2),
                'total': round(test_score, 2),
                'errors': test_errors
            }
            
            result['error_details'][test_name] = test_errors
            total_test_score += test_score
        
        # Calculate final algorithm score (scale to 70 points)
        max_total_score = len(self.test_cases) * 14  # 5 test cases × 14 points each = 70 points
        result['algorithm_score'] = min(70.0, total_test_score)  # Cap at 70 points
        result['total_score'] = result['algorithm_score']
        
        print(f"\n  Total Algorithm Score: {result['algorithm_score']:.1f}/70")
        print(f"  Execution Method: {result['execution_method']}")
        
        return result
    
    def grade_all_submissions(self) -> List[Dict]:
        """Grade all submissions in the submissions folder"""
        if not self.submissions_path.exists():
            print(f"Submissions path {self.submissions_path} not found!")
            return []
            
        results = []
        submission_folders = [f for f in self.submissions_path.iterdir() if f.is_dir()]
        
        print(f"Found {len(submission_folders)} submissions to grade")
        print("=" * 80)
        
        for i, submission_folder in enumerate(sorted(submission_folders), 1):
            print(f"\n[{i}/{len(submission_folders)}] ", end="")
            try:
                result = self.grade_submission(submission_folder)
                results.append(result)
                self.results.append(result)
            except Exception as e:
                print(f"Error grading {submission_folder.name}: {e}")
                traceback.print_exc()
                error_result = {
                    'submission': submission_folder.name,
                    'algorithm_score': 0,
                    'comments_score': 0,
                    'report_score': 0,
                    'total_score': 0,
                    'max_algorithm_score': 70,
                    'notes': [f"Grading error: {str(e)}"],
                    'has_makefile': 'Error',
                    'has_program_file': 'Error',
                    'execution_method': 'Error',
                    'makefile_location': 'N/A',
                    'program_file_location': 'N/A',
                    'test_results': {},
                    'error_details': {}
                }
                results.append(error_result)
                self.results.append(error_result)
        
        return results
    
    def generate_csv_report(self, results: List[Dict], output_file: str = "grading_results_strict.csv"):
        """Generate detailed CSV report with strict scoring breakdown"""
        if not results:
            print("No results to generate report!")
            return
            
        fieldnames = [
            'Submission', 
            'Has_Makefile',
            'Has_Program_File',
            'Execution_Method',
            'Makefile_Location',
            'Program_File_Location',
            'Algorithm_Score_70', 
            'Comments_Score_10', 
            'Report_Score_20',
            'Total_Score_100', 
            'Percentage'
        ]
        
        # Add individual test case columns with strict 1/3 breakdown
        for test_case in self.test_cases.keys():
            test_name = test_case.replace("input.txt", "").replace(".txt", "")
            fieldnames.extend([
                f"{test_name}_run_{self.points_per_mode:.1f}",
                f"{test_name}_ast_{self.points_per_mode:.1f}",
                f"{test_name}_st_{self.points_per_mode:.1f}",
                f"{test_name}_total_14",
                f"{test_name}_run_error",
                f"{test_name}_ast_error",
                f"{test_name}_st_error"
            ])
        
        fieldnames.extend(['General_Notes'])
        
        output_path = self.workspace_path / output_file
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                row = {
                    'Submission': result['submission'],
                    'Has_Makefile': result.get('has_makefile', 'Unknown'),
                    'Has_Program_File': result.get('has_program_file', 'Unknown'),
                    'Execution_Method': result.get('execution_method', 'Unknown'),
                    'Makefile_Location': result.get('makefile_location', 'N/A'),
                    'Program_File_Location': result.get('program_file_location', 'N/A'),
                    'Algorithm_Score_70': f"{result['algorithm_score']:.1f}",
                    'Comments_Score_10': result['comments_score'],
                    'Report_Score_20': result['report_score'],
                    'Total_Score_100': f"{result['total_score']:.1f}",
                    'Percentage': f"{result['total_score']:.1f}%"
                }
                
                # Add test case details with strict breakdown
                if 'test_results' in result:
                    for test_case in self.test_cases.keys():
                        test_name = test_case.replace("input.txt", "").replace(".txt", "")
                        if test_name in result['test_results']:
                            test_result = result['test_results'][test_name]
                            row[f"{test_name}_run_{self.points_per_mode:.1f}"] = test_result['run_score']
                            row[f"{test_name}_ast_{self.points_per_mode:.1f}"] = test_result['ast_score']
                            row[f"{test_name}_st_{self.points_per_mode:.1f}"] = test_result['st_score']
                            row[f"{test_name}_total_14"] = test_result['total']
                            
                            # Add error details
                            if 'errors' in test_result:
                                row[f"{test_name}_run_error"] = test_result['errors'].get('run', '')
                                row[f"{test_name}_ast_error"] = test_result['errors'].get('ast', '')
                                row[f"{test_name}_st_error"] = test_result['errors'].get('st', '')
                            else:
                                row[f"{test_name}_run_error"] = ''
                                row[f"{test_name}_ast_error"] = ''
                                row[f"{test_name}_st_error"] = ''
                        else:
                            row[f"{test_name}_run_{self.points_per_mode:.1f}"] = 0
                            row[f"{test_name}_ast_{self.points_per_mode:.1f}"] = 0
                            row[f"{test_name}_st_{self.points_per_mode:.1f}"] = 0
                            row[f"{test_name}_total_14"] = 0
                            row[f"{test_name}_run_error"] = 'Not tested'
                            row[f"{test_name}_ast_error"] = 'Not tested'
                            row[f"{test_name}_st_error"] = 'Not tested'
                
                row['General_Notes'] = "; ".join(result.get('notes', []))
                writer.writerow(row)
        
        print(f"\nStrict scoring CSV report generated: {output_path}")
        print("Features: Strict scoring, subfolder search, enhanced error handling")

    def run_grading(self):
        """Run the complete grading process with strict requirements"""
        print("Enhanced RPAL Assignment Automated Grading System - Strict Scoring Version")
        print("=" * 80)
        print("Key Features:")
        print("- Strict scoring: Perfect match = full points, errors = 0 points")
        print("- AST structure normalization (dots vs spaces)")
        print("- Subfolder search for Makefiles and program files")
        print("- Enhanced output comparison ignoring extra content")
        print("- Runtime error detection (traceback/exceptions = 0 marks)")
        print("- IDENTIFIER/ID token normalization")
        print("- Comprehensive error tracking")
        print("=" * 80)
        print("Grading Breakdown:")
        print(f"- Algorithm Correctness: 70 points (automated)")
        print(f"  - Each test case: 14 points ({self.points_per_mode:.1f} each for run/ast/st)")
        print("- Comments & Readability: 10 points (manual)")
        print("- Report: 20 points (manual)")
        print("=" * 80)
        
        # Check workspace structure
        if not self.workspace_path.exists():
            print(f"Error: Workspace path {self.workspace_path} does not exist!")
            return
            
        if not self.submissions_path.exists():
            print(f"Error: Submissions path {self.submissions_path} does not exist!")
            return
            
        if not self.test_cases_path.exists():
            print(f"Error: Test cases path {self.test_cases_path} does not exist!")
            return
        
        # Check test cases
        missing_files = []
        for input_file, (output_file, ast_file) in self.test_cases.items():
            if not (self.test_cases_path / input_file).exists():
                missing_files.append(input_file)
            if not (self.test_cases_path / output_file).exists():
                missing_files.append(output_file)
            if not (self.test_cases_path / ast_file).exists():
                missing_files.append(ast_file)
        
        if missing_files:
            print(f"Warning: Missing test case files: {missing_files}")
            continue_anyway = input("Continue anyway? (y/n): ").lower().startswith('y')
            if not continue_anyway:
                return
        
        # Grade all submissions
        results = self.grade_all_submissions()
        
        # Generate report
        self.generate_csv_report(results)
        
        # Print summary
        print("\n" + "=" * 80)
        print("GRADING SUMMARY - STRICT SCORING")
        print("=" * 80)
        
        if results:
            total_submissions = len(results)
            avg_algorithm_score = sum(r['algorithm_score'] for r in results) / total_submissions
            
            makefile_count = sum(1 for r in results if r.get('has_makefile') == 'Yes')
            execution_methods = {}
            for r in results:
                method = r.get('execution_method', 'Unknown')
                execution_methods[method] = execution_methods.get(method, 0) + 1
            
            print(f"Total Submissions: {total_submissions}")
            print(f"Average Algorithm Score: {avg_algorithm_score:.1f}/70 ({avg_algorithm_score/70*100:.1f}%)")
            print(f"Submissions with Makefile: {makefile_count}")
            print("Execution Methods:")
            for method, count in execution_methods.items():
                print(f"  {method}: {count}")
            
            # Show score distribution
            score_ranges = {"0-10": 0, "11-20": 0, "21-30": 0, "31-40": 0, "41-50": 0, "51-60": 0, "61-70": 0}
            for result in results:
                score = result['algorithm_score']
                if score <= 10: score_ranges["0-10"] += 1
                elif score <= 20: score_ranges["11-20"] += 1
                elif score <= 30: score_ranges["21-30"] += 1
                elif score <= 40: score_ranges["31-40"] += 1
                elif score <= 50: score_ranges["41-50"] += 1
                elif score <= 60: score_ranges["51-60"] += 1
                else: score_ranges["61-70"] += 1
            
            print("\nAlgorithm Score Distribution:")
            for range_name, count in score_ranges.items():
                print(f"  {range_name}: {count} submissions")
            
            # Show top and bottom performers
            sorted_results = sorted(results, key=lambda x: x['algorithm_score'], reverse=True)
            print(f"\nTop 3 Performers:")
            for i, result in enumerate(sorted_results[:3], 1):
                print(f"  {i}. {result['submission']}: {result['algorithm_score']:.1f}/70")
            
            if len(sorted_results) > 3:
                print(f"\nNeeds Attention (Bottom 3):")
                for i, result in enumerate(sorted_results[-3:], 1):
                    print(f"  {i}. {result['submission']}: {result['algorithm_score']:.1f}/70")
            
        print(f"\nGrading completed! Check the CSV file for detailed results.")
        print("Remember to manually add Comments (10 pts) and Report (20 pts) scores.")


def main():
    """Main function to run the grader"""
    if len(sys.argv) > 1:
        workspace_path = sys.argv[1]
    else:
        workspace_path = input("Enter path to grading_workspace (or press Enter for current directory): ").strip()
        if not workspace_path:
            workspace_path = "."
    
    # Initialize and run grader
    grader = RPALGrader(workspace_path)
    grader.run_grading()

if __name__ == "__main__":
    main()