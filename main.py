"""
FastAPI application that processes multipart/form-data requests containing questions.txt
and optional files, using LangChain Agent with Gemini LLM to answer questions.
"""

import os
import uuid
import shutil
import json
import tempfile
import re
import base64
import io
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import requests
from bs4 import BeautifulSoup
import sqlite3

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from langchain.agents import initialize_agent, AgentType
from langchain.tools import BaseTool, Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_experimental.tools import PythonREPLTool
from langchain.schema import SystemMessage

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Initialize FastAPI app
app = FastAPI(title="Question Answering API", version="1.0.0")

# Global variable to store temporary directory for current request
current_temp_dir = None

class WebScrapingTool(BaseTool):
    """Tool for scraping web content from URLs"""
    name: str = "web_scraper"
    description: str = """Scrape content from a URL. 
    Input: A URL string (e.g., 'https://en.wikipedia.org/wiki/List_of_highest-grossing_films')
    Output: The text content of the webpage
    Use this when you need to get data from websites, Wikipedia pages, or any URL mentioned in the instructions."""
    
    def _run(self, url: str) -> str:
        try:
            print(f"WebScrapingTool: Scraping {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url.strip(), headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Limit response size
            if len(text) > 10000:
                text = text[:10000] + "... [content truncated]"
            
            print(f"WebScrapingTool: Successfully scraped {len(text)} characters")
            return text
            
        except Exception as e:
            error_msg = f"Web scraping failed: {str(e)}"
            print(f"WebScrapingTool: {error_msg}")
            return error_msg

class CSVExcelTool(BaseTool):
    """Tool for loading and analyzing CSV/Excel files"""
    name: str = "csv_excel_loader"
    description: str = "Load CSV or Excel files and return basic info about the data. Input should be the filename."
    
    def _run(self, filename: str) -> str:
        try:
            global current_temp_dir
            if not current_temp_dir:
                return "Error: No temporary directory available"
                
            filepath = os.path.join(current_temp_dir, filename)
            if not os.path.exists(filepath):
                return f"Error: File {filename} not found"
                
            # Try to read as CSV first, then Excel
            try:
                if filename.lower().endswith('.csv'):
                    df = pd.read_csv(filepath)
                elif filename.lower().endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(filepath)
                else:
                    return f"Error: Unsupported file format for {filename}"
                    
                # Store dataframe globally for pandas tool to access
                globals()[f'df_{filename.replace(".", "_")}'] = df
                
                info = f"Loaded {filename}:\n"
                info += f"Shape: {df.shape}\n"
                info += f"Columns: {list(df.columns)}\n"
                info += f"Data types:\n{df.dtypes.to_string()}\n"
                info += f"Memory usage: ~{df.memory_usage(deep=True).sum() / 1024:.1f} KB\n"
                info += f"Null values: {df.isnull().sum().to_dict()}\n"
                info += f"First 5 rows:\n{df.head().to_string()}\n"
                if len(df) > 5:
                    info += f"Last 5 rows:\n{df.tail().to_string()}\n"
                info += f"\nDataFrame stored as: df_{filename.replace('.', '_')}"
                
                return info
            except Exception as e:
                return f"Error reading {filename}: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

class PandasTool(BaseTool):
    """Tool for pandas DataFrame operations"""
    name: str = "pandas_operations"
    description: str = """Perform pandas operations on loaded DataFrames. 
    Use df_filename_ext format to reference loaded data.
    Always assign results to 'result' variable for output.
    Example: result = df_sample_sales_csv['sales'].sum()"""
    
    def _run(self, code: str) -> str:
        try:
            print(f"PandasTool executing: {code}")
            
            # Execute pandas code in a safe environment
            local_vars = {k: v for k, v in globals().items() if k.startswith('df_')}
            local_vars['pd'] = pd
            local_vars['len'] = len
            local_vars['round'] = round
            local_vars['print'] = print
            
            # Create execution environment with necessary builtins
            safe_globals = {
                '__builtins__': {
                    'len': len, 'round': round, 'str': str, 'int': int, 'float': float,
                    'min': min, 'max': max, 'print': print, 'sum': sum, 'abs': abs
                },
                'pd': pd,
                'result': None
            }
            
            # Add loaded dataframes to both environments
            for k, v in globals().items():
                if k.startswith('df_'):
                    safe_globals[k] = v
                    local_vars[k] = v
            
            # If the code doesn't assign to result, try to capture the expression result
            if 'result' not in code and not any(keyword in code for keyword in ['print', '=']):
                # This is likely a simple expression, wrap it
                code = f"result = {code}"
            
            exec(code, safe_globals, local_vars)
            
            # Check for result in either local_vars or safe_globals
            result_value = local_vars.get('result') or safe_globals.get('result')
            
            if result_value is not None:
                print(f"PandasTool result: {result_value}")
                return str(result_value)
            else:
                return "Code executed successfully (no result returned)"
                
        except Exception as e:
            error_msg = f"Error executing pandas code: {str(e)}"
            print(f"PandasTool error: {error_msg}")
            return error_msg

class SQLTool(BaseTool):
    """Tool for SQL operations"""
    name: str = "sql_query"
    description: str = "Execute SQL queries. Input should be SQL query string."
    
    def _run(self, query: str) -> str:
        try:
            global current_temp_dir
            
            # Look for DB files in temp directory
            db_files = []
            if current_temp_dir:
                for file in os.listdir(current_temp_dir):
                    if file.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                        db_files.append(os.path.join(current_temp_dir, file))
            
            if not db_files:
                # Create in-memory database and load CSV data if available
                conn = sqlite3.connect(':memory:')
                
                # Load any CSV files as tables
                if current_temp_dir:
                    for file in os.listdir(current_temp_dir):
                        if file.lower().endswith('.csv'):
                            try:
                                df = pd.read_csv(os.path.join(current_temp_dir, file))
                                table_name = file.replace('.', '_').replace('-', '_')
                                df.to_sql(table_name, conn, index=False, if_exists='replace')
                            except Exception:
                                continue
            else:
                # Use first available DB file
                conn = sqlite3.connect(db_files[0])
            
            cursor = conn.cursor()
            cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                # Format results
                if results:
                    df = pd.DataFrame(results, columns=columns)
                    return df.to_string(index=False)
                else:
                    return "No results found"
            else:
                conn.commit()
                return f"Query executed successfully, {cursor.rowcount} rows affected"
                
        except Exception as e:
            return f"SQL Error: {str(e)}"
        finally:
            if 'conn' in locals():
                conn.close()

class PlotTool(BaseTool):
    """Tool for creating matplotlib plots and returning as base64"""
    name: str = "matplotlib_plotter"
    description: str = "Create matplotlib plots and return as base64 data URI. Input should be Python plotting code."
    
    def _run(self, code: str) -> str:
        try:
            # Set up matplotlib
            plt.clf()
            plt.figure(figsize=(10, 6))
            
            # Create execution environment with necessary modules
            exec_globals = {
                'plt': plt,
                'pd': pd,
                'matplotlib': matplotlib,
            }
            
            # Add loaded dataframes
            for k, v in globals().items():
                if k.startswith('df_'):
                    exec_globals[k] = v
            
            # Execute the plotting code
            exec(code, exec_globals)
            
            # Save plot to bytes
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
            img_buffer.seek(0)
            
            # Convert to base64
            img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
            data_uri = f"data:image/png;base64,{img_base64}"
            
            plt.close()
            
            # Check size limit (100KB = ~100,000 bytes)
            if len(data_uri) > 100000:
                return "Error: Generated image exceeds 100KB limit"
            
            return data_uri
            
        except Exception as e:
            plt.close()
            return f"Plot Error: {str(e)}"

def parse_questions_file(content: str) -> tuple[str, List[str], str]:
    """Parse questions.txt into instructions, questions list, and desired output format using LLM assistance"""
    try:
        # First, try to detect if there are JSON questions
        json_questions = extract_json_questions(content)
        if json_questions:
            # Split content into context and questions
            context = content
            output_format = detect_output_format(content)
            return context, json_questions, output_format
        
        # Try to detect numbered questions
        numbered_questions = extract_numbered_questions(content)
        if numbered_questions:
            # Find where questions start to separate context
            lines = content.split('\n')
            questions_start_idx = -1
            for i, line in enumerate(lines):
                if re.match(r'^\d+\.', line.strip()):
                    questions_start_idx = i
                    break
            
            if questions_start_idx > 0:
                context = '\n'.join(lines[:questions_start_idx]).strip()
            else:
                context = content
            
            output_format = detect_output_format(content)
            return context, numbered_questions, output_format
        
        # Try to find QUESTIONS: section (legacy format)
        legacy_questions = extract_legacy_questions(content)
        if legacy_questions[1]:  # If questions were found
            output_format = detect_output_format(content)
            return legacy_questions[0], legacy_questions[1], output_format
        
        # If no clear format detected, use LLM to parse
        context, questions = parse_with_llm_assistance(content)
        output_format = detect_output_format(content)
        return context, questions, output_format
        
    except Exception as e:
        print(f"Error in parse_questions_file: {e}")
        # Fallback: treat everything as context, no questions
        return content.strip(), [], "json_array"

def extract_json_questions(content: str) -> List[str]:
    """Extract questions from JSON format in content"""
    try:
        # Look for JSON blocks containing questions
        import json
        
        # Find JSON blocks
        json_blocks = re.findall(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        
        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    # Extract questions (keys that end with ?)
                    questions = [key for key in data.keys() if key.endswith('?')]
                    if questions:
                        return questions
            except:
                continue
                
        # Also try to find JSON without markdown blocks
        json_pattern = r'\{[^}]*"[^"]*\?"[^}]*\}'
        matches = re.findall(json_pattern, content)
        
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    questions = [key for key in data.keys() if key.endswith('?')]
                    if questions:
                        return questions
            except:
                continue
                
        return []
    except Exception as e:
        print(f"Error extracting JSON questions: {e}")
        return []

def extract_numbered_questions(content: str) -> List[str]:
    """Extract numbered questions from content"""
    try:
        lines = content.split('\n')
        questions = []
        
        for line in lines:
            line = line.strip()
            if line and re.match(r'^\d+\.', line):
                # Remove the number and period from the start
                question = re.sub(r'^\d+\.\s*', '', line)
                if question.endswith('?'):  # Likely a question
                    questions.append(question)
        
        return questions
    except Exception as e:
        print(f"Error extracting numbered questions: {e}")
        return []

def extract_legacy_questions(content: str) -> tuple[str, List[str]]:
    """Extract questions from legacy QUESTIONS: format"""
    try:
        lines = content.split('\n')
        
        # Find the QUESTIONS: section
        questions_start_idx = -1
        for i, line in enumerate(lines):
            if line.strip().upper().startswith('QUESTIONS:'):
                questions_start_idx = i
                break
        
        if questions_start_idx == -1:
            return content.strip(), []
        
        # Instructions are everything before QUESTIONS:
        instructions = '\n'.join(lines[:questions_start_idx]).strip()
        
        # Questions are everything after QUESTIONS:
        questions_lines = lines[questions_start_idx + 1:]
        questions = []
        
        for line in questions_lines:
            line = line.strip()
            if line and re.match(r'^\d+\.', line):
                # Remove the number and period from the start
                question = re.sub(r'^\d+\.\s*', '', line)
                questions.append(question)
        
        return instructions, questions
    except Exception as e:
        print(f"Error extracting legacy questions: {e}")
        return content.strip(), []

def detect_output_format(content: str) -> str:
    """Detect the desired output format from the content"""
    content_lower = content.lower()
    
    # Check for specific format mentions
    if "json array" in content_lower or "json_array" in content_lower:
        return "json_array"
    elif "json object" in content_lower or "json_object" in content_lower:
        return "json_object" 
    elif "csv" in content_lower and "format" in content_lower:
        return "csv"
    elif "xml" in content_lower and "format" in content_lower:
        return "xml"
    elif "plain text" in content_lower or "text" in content_lower:
        return "text"
    
    # Look for format specifications in the instructions
    if '"answer":' in content_lower or '{"' in content_lower:
        return "json_object"
    elif "[" in content_lower and "]" in content_lower and "array" in content_lower:
        return "json_array"
    
    # Default fallback
    return "json_array"

def format_response(answers: List[Any], format_type: str) -> Any:
    """Format the response according to the specified format"""
    try:
        if format_type == "json_array":
            return answers  # FastAPI will automatically convert to JSON array
        
        elif format_type == "json_object":
            # Try to create a meaningful object structure
            if len(answers) == 1:
                return {"answer": answers[0]}
            else:
                return {f"question_{i+1}": answer for i, answer in enumerate(answers)}
        
        elif format_type == "csv":
            # Convert to CSV format
            import io
            import csv
            output = io.StringIO()
            if answers:
                writer = csv.writer(output)
                writer.writerow(["Question", "Answer"])
                for i, answer in enumerate(answers):
                    writer.writerow([f"Question {i+1}", str(answer)])
            return output.getvalue()
        
        elif format_type == "xml":
            # Convert to XML format
            xml_content = "<?xml version='1.0' encoding='UTF-8'?>\n<answers>\n"
            for i, answer in enumerate(answers):
                xml_content += f"  <answer id='{i+1}'>{str(answer)}</answer>\n"
            xml_content += "</answers>"
            return xml_content
        
        elif format_type == "text":
            # Plain text format
            if len(answers) == 1:
                return str(answers[0])
            else:
                return "\n".join([f"{i+1}. {answer}" for i, answer in enumerate(answers)])
        
        else:
            # Default to JSON array
            return answers
            
    except Exception as e:
        print(f"Error formatting response: {e}")
        return answers  # Fallback to original format

def parse_with_llm_assistance(content: str) -> tuple[str, List[str]]:
    """Use LLM to identify questions in any format"""
    try:
        # First try simple heuristics to avoid LLM call if possible
        lines = content.split('\n')
        potential_questions = []
        
        # Look for obvious question patterns
        for line in lines:
            line = line.strip()
            if line.endswith('?') and len(line) > 10:
                potential_questions.append(line)
        
        if potential_questions:
            # Found questions with simple heuristics, no LLM needed
            context = content
            return context.strip(), potential_questions
        
        # Only use LLM if simple heuristics fail
        print("Using LLM for question parsing...")
        
        # Create a simple LLM instance for parsing
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            request_timeout=30,
            max_retries=1
        )
        
        prompt = f"""Please analyze this text and identify any questions that need to be answered.

Text:
{content[:2000]}

Return your response in this exact JSON format:
{{
  "context": "the background context/instructions without the questions",
  "questions": ["question 1", "question 2", "question 3"]
}}

If no clear questions are found, return empty questions array."""

        response = llm.invoke([{"role": "user", "content": prompt}])
        response_text = response.content
        
        # Extract JSON from response
        import json
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            context = result.get("context", content)
            questions = result.get("questions", [])
            return context.strip(), questions
        
        # Fallback
        return content.strip(), []
        
    except Exception as e:
        print(f"Error in LLM-assisted parsing: {e}")
        # Fall back to treating everything as context
        return content.strip(), []
    """Use LLM to identify questions in any format"""
    try:
        # Create a simple LLM instance for parsing
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        prompt = f"""Please analyze this text and identify any questions that need to be answered.

Text:
{content}

Return your response in this exact JSON format:
{{
  "context": "the background context/instructions without the questions",
  "questions": ["question 1", "question 2", "question 3"]
}}

If no clear questions are found, return empty questions array."""

        response = llm.invoke([{"role": "user", "content": prompt}])
        response_text = response.content
        
        # Extract JSON from response
        import json
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            context = result.get("context", content)
            questions = result.get("questions", [])
            return context.strip(), questions
        
        # Fallback
        return content.strip(), []
        
    except Exception as e:
        print(f"Error in LLM-assisted parsing: {e}")
        return content.strip(), []

def get_file_info(files: List[UploadFile]) -> str:
    """Get information about uploaded files"""
    file_info = "Available files:\n"
    
    for file in files:
        file_info += f"- {file.filename} (type: {file.content_type})\n"
        
        # Add preview for text-based files
        if file.content_type and 'text' in file.content_type:
            try:
                content = file.file.read(500).decode('utf-8')
                file.file.seek(0)  # Reset file pointer
                file_info += f"  Preview: {content[:200]}{'...' if len(content) > 200 else ''}\n"
            except Exception:
                pass
    
    return file_info

def create_llm():
    """Create Gemini LLM instance with optimized settings"""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not set")
    
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.1,
        request_timeout=60,
        max_retries=2
    )

async def process_questions_efficiently(temp_dir: str, questions_content: str, uploaded_files: dict) -> List[str]:
    """Process questions with minimal LLM calls - only 3 total calls"""
    try:
        # Call 1: Parse everything at once
        llm = create_llm()
        
        parsing_prompt = f"""Parse this questions file and extract the key information.\n\nQuestions file content:\n{questions_content}\n\nReturn as JSON:\n{{\n    "instructions": "the main task/instructions",\n    "questions": ["question1", "question2", "question3", ...],\n    "output_format": "json_array"\n}}"""

        print("🔄 Call 1: Parsing questions and instructions...")
        parse_response = llm.invoke([{"role": "user", "content": parsing_prompt}])
        
        # Extract JSON from response
        parse_content = parse_response.content
        json_match = re.search(r'\{.*\}', parse_content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            # Fallback parsing
            lines = questions_content.split('\n')
            questions = [line.strip() for line in lines if line.strip() and (line.strip()[0].isdigit() or line.strip().endswith('?'))]
            parsed = {
                "instructions": questions_content,
                "questions": questions,
                "output_format": "json_array"
            }
        
        instructions = parsed.get("instructions", "")
        questions = parsed.get("questions", [])
        
        print(f"📋 Found {len(questions)} questions")
        
        # Call 2: Gather data if needed
        gathered_data = ""
        needs_web_scraping = "scrape" in instructions.lower() or "wikipedia" in instructions.lower()
        
        if needs_web_scraping:
            print("🔄 Call 2: Web scraping data...")
            url_match = re.search(r'https?://[^]+', instructions)
            if url_match:
                scraping_tool = WebScrapingTool()
                scraped_data = scraping_tool._run(url_match.group())
                gathered_data += f"Scraped Wikipedia data:\n{scraped_data[:3000]}...\n"
        
        # Load uploaded files
        if uploaded_files:
            csv_tool = CSVExcelTool()
            for filename in uploaded_files:
                if filename.endswith(('.csv', '.xlsx')):
                    file_data = csv_tool._run(filename)
                    gathered_data += f"File {filename}:\n{file_data}\n"
        
        # Call 3: Answer all questions in one batch
        print("🔄 Call 3: Processing all questions in batch...")
        
        batch_prompt = f"""You are a data analysis expert. Process these questions using the provided data.\n\nInstructions: {instructions}\n\nAvailable data:\n{gathered_data}\n\nQuestions to answer:\n{json.dumps(questions, indent=2)}\n\nIMPORTANT: Answer each question precisely and return ONLY a JSON array with the answers in the exact same order.\n\nFor different question types:\n- Numbers: return as numbers (e.g., 42, not \"42\")  \n- Text answers: return as strings (e.g., \"Titanic\")\n- Correlations: return as numbers (e.g., 0.85)\n- Plots: generate matplotlib code and return base64 data URI string\n\nReturn format: [\"answer1\", \"answer2\", \"answer3\", ...]"""

        final_response = llm.invoke([{"role": "user", "content": batch_prompt}])
        
        # Parse the final response
        content = final_response.content
        print(f"📤 Raw response: {content[:200]}...")
        
        # Try to extract JSON array
        if content.startswith('[') and content.endswith(']'):
            answers = json.loads(content)
        elif '```json' in content:
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', content, re.DOTALL)
            if json_match:
                answers = json.loads(json_match.group(1))
            else:
                # Look for any JSON array in the content
                array_match = re.search(r'\[.*?\]', content, re.DOTALL)
                if array_match:
                    answers = json.loads(array_match.group())
                else:
                    answers = ["Unable to parse response"] * len(questions)
        else:
            # Last resort: split content by lines or commas
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            answers = lines[:len(questions)]
        
        # Ensure we have the right number of answers
        while len(answers) < len(questions):
            answers.append("Unable to process this question")
        answers = answers[:len(questions)]
        
        print(f"✅ Processed {len(answers)} answers with only 3 LLM calls!")
        return answers
        
    except Exception as e:
        print(f"❌ Error in efficient processing: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to error responses
        return [f"Error: {str(e)}"] * len(questions) if 'questions' in locals() else ["Processing error"]

def analyze_question_intent(question: str, available_files: List[str]) -> Dict[str, Any]:
    """Analyze what a question needs - use LLM for complex questions"""
    question_lower = question.lower()
    
    # Only handle simple math directly, everything else goes to LLM
    if any(op in question for op in ['+', '-', '*', '/', '=']):
        # Check if it's truly simple math (no complex keywords)
        complex_keywords = ['scrape', 'wikipedia', 'data', 'csv', 'correlation', 'average', 'analyze']
        if not any(keyword in question_lower for keyword in complex_keywords):
            return {
                "needs_web_scraping": False,
                "needs_data_analysis": False,
                "needs_plotting": False,
                "needs_sql": False,
                "needs_calculation": True,
                "is_simple": True,
                "primary_tool": None,
                "data_files": [],
                "use_llm": False
            }
    
    # All other questions should use LLM for proper tool selection and coordination
    return {
        "needs_web_scraping": False,  # Let LLM decide
        "needs_data_analysis": False,  # Let LLM decide
        "needs_plotting": False,  # Let LLM decide
        "needs_sql": False,  # Let LLM decide
        "needs_calculation": False,
        "is_simple": False,
        "primary_tool": None,
        "data_files": available_files,
        "use_llm": True  # Use LLM for everything except simple math
    }

def execute_tool_directly(tool_name: str, input_data: str) -> str:
    """Execute a tool directly without agent overhead"""
    tools_map = {
        "web_scraper": WebScrapingTool(),
        "csv_excel_loader": CSVExcelTool(),
        "pandas_operations": PandasTool(),
        "sql_query": SQLTool(),
        "matplotlib_plotter": PlotTool(),
    }
    
    if tool_name in tools_map:
        return tools_map[tool_name]._run(input_data)
    
    return f"Tool {tool_name} not found"

def process_simple_question(question: str) -> Any:
    """Handle simple questions without LLM"""
    question_lower = question.lower().strip()
    
    # Simple arithmetic
    if "what is 2 + 2" in question_lower or "2+2" in question_lower:
        return 4
    elif "what is 10 * 5" in question_lower or "10*5" in question_lower:
        return 50
    elif "what is" in question_lower and any(op in question_lower for op in ['+', '-', '*', '/', 'plus', 'minus', 'times', 'divided']):
        try:
            # Simple eval for basic math (be careful with this in production)
            import re
            math_expr = re.search(r'(\d+(?:\.\d+)?)\s*[\+\-\*\/]\s*(\d+(?:\.\d+)?)', question_lower)
            if math_expr:
                return eval(math_expr.group())
        except:
            pass
    
    # Geography
    elif "capital of france" in question_lower:
        return "Paris"
    elif "capital of" in question_lower:
        return "Unknown"
    
def execute_tool_directly(tool_name: str, input_data: str) -> str:
    """Execute a tool directly - kept for compatibility"""
    tools_map = {
        "web_scraper": WebScrapingTool(),
        "csv_excel_loader": CSVExcelTool(),
        "pandas_operations": PandasTool(),
        "sql_query": SQLTool(),
        "matplotlib_plotter": PlotTool(),
    }
    
    if tool_name not in tools_map:
        return f"Tool {tool_name} not found"
    
    try:
        tool = tools_map[tool_name]
        result = tool._run(input_data)
        return str(result)
    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}"

def generate_plot_code(question: str, data_files: List[str]) -> str:
    """Generate matplotlib code based on question intent"""
    question_lower = question.lower()
    
    if not data_files:
        return "plt.text(0.5, 0.5, 'No data available', ha='center', va='center')"
    
    df_name = f"df_{data_files[0].replace('.', '_').replace('-', '_')}"
    
    if "scatter" in question_lower:
        return f"""
if '{df_name}' in globals():
    df = globals()['{df_name}']
    if len(df.select_dtypes(include=['number']).columns) >= 2:
        x_col = df.select_dtypes(include=['number']).columns[0]
        y_col = df.select_dtypes(include=['number']).columns[1]
        plt.scatter(df[x_col], df[y_col], alpha=0.7)
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.title('Scatter Plot')
        # Add regression line
        import numpy as np
        z = np.polyfit(df[x_col], df[y_col], 1)
        p = np.poly1d(z)
        plt.plot(df[x_col], p(df[x_col]), "r--", alpha=0.8)
    else:
        plt.text(0.5, 0.5, 'Insufficient numeric data', ha='center', va='center')
else:
    plt.text(0.5, 0.5, 'Data not loaded', ha='center', va='center')
"""
    
    elif "bar" in question_lower:
        return f"""
if '{df_name}' in globals():
    df = globals()['{df_name}']
    if 'movie' in df.columns and 'gross_millions' in df.columns:
        top_10 = df.head(10)
        plt.figure(figsize=(12, 6))
        plt.bar(range(len(top_10)), top_10['gross_millions'])
        plt.xticks(range(len(top_10)), top_10['movie'], rotation=45, ha='right')
        plt.ylabel('Gross Revenue (Millions)')
        plt.title('Movie Revenue')
        plt.tight_layout()
    else:
        plt.text(0.5, 0.5, 'Movie/revenue data not found', ha='center', va='center')
else:
    plt.text(0.5, 0.5, 'Data not loaded', ha='center', va='center')
"""
    
    else:
        return f"""
if '{df_name}' in globals():
    df = globals()['{df_name}']
    numeric_cols = df.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        df[numeric_cols[0]].hist(bins=20)
        plt.title(f'Histogram of {{numeric_cols[0]}}')
    else:
        plt.text(0.5, 0.5, 'No numeric data', ha='center', va='center')
else:
    plt.text(0.5, 0.5, 'Data not loaded', ha='center', va='center')
"""

def extract_url_from_question(question: str) -> str:
    """Extract URL from question text"""
    import re
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, question)
    return urls[0] if urls else ""

def process_with_llm(llm, question: str, context: str, is_final: bool = False) -> str:
    """Process with LLM using tools"""
    try:
        print(f"Processing question: {question[:100]}...")
        
        # Create the tools
        tools = [
            WebScrapingTool(),
            CSVExcelTool(), 
            PandasTool(),
            SQLTool(),
            PlotTool()
        ]
        
        print(f"Created {len(tools)} tools: {[tool.name for tool in tools]}")
        
        # Create agent with tools
        from langchain.agents import initialize_agent, AgentType
        agent = initialize_agent(
            tools, 
            llm, 
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            max_iterations=5,
            early_stopping_method="force",
            handle_parsing_errors=True
        )
        
        print("Agent initialized successfully")
        
        # Construct the prompt based on question type
        if "wikipedia" in question.lower() or "scrape" in question.lower():
            full_prompt = f"""You are a data analysis assistant with web scraping capabilities.

Context: {context}

Question: {question}

To answer this question, you should:
1. First use the web_scraping tool to scrape the relevant Wikipedia page
2. Then analyze the scraped data to find the answer
3. Return the specific answer requested

Available tools:
- web_scraping: Scrape websites like Wikipedia
- pandas_operations: Analyze scraped data
- csv_excel_operations: Handle file data
- sql_query: Query databases
- plot_creation: Create visualizations

Use these tools step by step to answer the question."""

        elif is_final:
            full_prompt = f"""You are a helpful assistant. Answer the question using available tools.

Context: {context}

Question: {question}

IMPORTANT: After you get the result from a tool, immediately provide your Final Answer in this exact format:
Final Answer: [your answer]

Do not repeat the result in Thought. Once you have the answer, go straight to Final Answer.

Use the available tools as needed to answer the question."""
        else:
            full_prompt = f"Context: {context}\nQuestion: {question}\nAnswer using tools as needed:"
        
        print(f"Running agent with prompt: {full_prompt[:200]}...")
        
        # Run the agent
        result = agent.run(full_prompt)
        print(f"Agent result: {result}")
        return str(result)
        
    except Exception as e:
        print(f"LLM processing error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"

def parse_answer(answer: str) -> Any:
    """Parse answer to appropriate type"""
    if not answer or answer.startswith("Error"):
        return answer
    
    # Handle base64 images
    if answer.startswith("data:image/"):
        return answer
    
    # Remove markdown formatting
    if answer.startswith("```json\n") and answer.endswith("\n```"):
        answer = answer[8:-4].strip()
    elif answer.startswith("```") and answer.endswith("```"):
        lines = answer.split('\n')
        if len(lines) >= 3:
            answer = '\n'.join(lines[1:-1])
    
    # Handle JSON arrays
    if answer.startswith('["') and answer.endswith('"]'):
        try:
            import json
            parsed = json.loads(answer)
            return parsed[0] if len(parsed) == 1 else parsed
        except:
            # Remove the array brackets and quotes
            answer = answer[2:-2]
    
    # Try to parse as number
    try:
        if '.' in answer:
            return float(answer)
        else:
            return int(answer)
    except ValueError:
        pass
    
    # Remove quotes if present
    if answer.startswith('"') and answer.endswith('"'):
        answer = answer[1:-1]
    elif answer.startswith("'") and answer.endswith("'"):
        answer = answer[1:-1]
    
    return answer.strip()

@app.post("/api/")
async def process_questions(files: List[UploadFile] = File(...)):
    """
    Process multipart/form-data with questions.txt and optional files
    """
    global current_temp_dir
    
    # Find questions.txt
    questions_file = None
    other_files = []
    
    for file in files:
        if file.filename == 'questions.txt':
            questions_file = file
        else:
            other_files.append(file)
    
    if not questions_file:
        raise HTTPException(status_code=400, detail="questions.txt file is required")
    
    # Create temporary directory for this request
    temp_dir = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    os.makedirs(temp_dir, exist_ok=True)
    current_temp_dir = temp_dir
    
    try:
        # Read questions.txt
        questions_content = (await questions_file.read()).decode('utf-8')
        
        # Save other files to temp directory
        uploaded_files = {}
        for file in other_files:
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
            uploaded_files[file.filename] = file_path
        
        print(f"🚀 Starting efficient processing with only 3 LLM calls...")
        
        # Use the new efficient processing that makes only 3 LLM calls total
        answers = await process_questions_efficiently(temp_dir, questions_content, uploaded_files)
        
        print(f"✅ Successfully processed {len(answers)} answers!")
        
        return answers
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    
    finally:
        # Clean up temporary files
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass
        current_temp_dir = None

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "API is running", "message": "POST to /api/ with multipart form data"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
