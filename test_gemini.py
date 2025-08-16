"""
Simple FastAPI application to test Gemini API with GUI
"""
import os
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Gemini API Tester")

class TestResponse(BaseModel):
    success: bool
    response: str
    model: str
    error: str = None

@app.get("/", response_class=HTMLResponse)
async def get_gui():
    """Serve the GUI"""
    # Get API key display string
    api_key = os.getenv('GEMINI_API_KEY', '')
    api_key_display = f"{api_key[:10]}..." if api_key else "Not set"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gemini API Tester</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
            .container {{ background: #f5f5f5; padding: 20px; border-radius: 10px; }}
            textarea {{ width: 100%; height: 150px; margin: 10px 0; }}
            button {{ background: #4CAF50; color: white; padding: 15px 32px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }}
            button:hover {{ background: #45a049; }}
            .result {{ background: white; padding: 15px; border-radius: 5px; margin-top: 20px; white-space: pre-wrap; }}
            .error {{ background: #ffebee; border-left: 4px solid #f44336; }}
            .success {{ background: #e8f5e8; border-left: 4px solid #4CAF50; }}
            .info {{ background: #e3f2fd; border-left: 4px solid #2196F3; }}
            h1 {{ color: #333; }}
            label {{ font-weight: bold; display: block; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Gemini API Tester</h1>
            
            <div class="info result">
                <strong>Current API Key:</strong> {api_key_display}<br>
                <strong>Available Models:</strong> gemini-2.5-flash, gemini-2.5-pro<br>
                <strong>Rate Limits:</strong> Free tier = 10 requests/minute
            </div>
            
            <form id="testForm">
                <label for="prompt">Enter your prompt:</label>
                <textarea id="prompt" name="prompt" placeholder="Ask me anything...">What is the capital of France?</textarea>
                
                <label for="model">Select Model:</label>
                <select id="model" name="model">
                    <option value="gemini-2.5-flash">gemini-2.5-flash (Faster, cheaper)</option>
                    <option value="gemini-2.5-pro">gemini-2.5-pro (More capable)</option>
                </select>
                
                <br><br>
                <button type="button" onclick="testAPI()">🧪 Test API</button>
                <button type="button" onclick="quickTest()">⚡ Quick Test</button>
                <button type="button" onclick="clearResults()">🧹 Clear Results</button>
            </form>
            
            <div id="results"></div>
        </div>
        
        <script>
            async function testAPI() {{
                const prompt = document.getElementById('prompt').value;
                const model = document.getElementById('model').value;
                
                if (!prompt.trim()) {{
                    showResult('Please enter a prompt!', 'error');
                    return;
                }}
                
                showResult('🔄 Testing API...', 'info');
                
                try {{
                    const response = await fetch('/test', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }},
                        body: `prompt=${{encodeURIComponent(prompt)}}&model=${{encodeURIComponent(model)}}`
                    }});
                    
                    const result = await response.json();
                    
                    if (result.success) {{
                        showResult(`✅ Success!\\n\\nModel: ${{result.model}}\\nResponse: ${{result.response}}`, 'success');
                    }} else {{
                        showResult(`❌ Error: ${{result.error}}`, 'error');
                    }}
                }} catch (error) {{
                    showResult(`❌ Network Error: ${{error.message}}`, 'error');
                }}
            }}
            
            async function quickTest() {{
                document.getElementById('prompt').value = 'Say hello and tell me what model you are.';
                await testAPI();
            }}
            
            function showResult(message, type) {{
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = `<div class="result ${{type}}">${{message}}</div>`;
            }}
            
            function clearResults() {{
                document.getElementById('results').innerHTML = '';
            }}
        </script>
    </body>
    </html>
    """
    
    return html_content

@app.post("/test")
async def test_gemini_api(prompt: str = Form(...), model: str = Form("gemini-2.5-flash")):
    """Test the Gemini API with a prompt"""
    
    # Check if API key is set
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return TestResponse(
            success=False,
            response="",
            model=model,
            error="GEMINI_API_KEY environment variable not set in .env file"
        )
    
    try:
        # Create LLM instance
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.1,
            request_timeout=30,
            max_retries=1
        )
        
        # Test the API
        response = llm.invoke([{"role": "user", "content": prompt}])
        
        return TestResponse(
            success=True,
            response=response.content,
            model=model
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # Provide helpful error messages
        if "429" in error_msg or "ResourceExhausted" in error_msg:
            error_msg = "Rate limit exceeded! You're hitting the 10 requests/minute limit on the free tier. Wait a minute and try again."
        elif "401" in error_msg or "Unauthorized" in error_msg:
            error_msg = "Invalid API key! Check your GEMINI_API_KEY in the .env file."
        elif "400" in error_msg:
            error_msg = "Bad request! Check your prompt or model selection."
        
        return TestResponse(
            success=False,
            response="",
            model=model,
            error=error_msg
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "gemini_api_key_set": bool(os.getenv('GEMINI_API_KEY')),
        "api_key_prefix": f"{os.getenv('GEMINI_API_KEY', '')[:10]}..." if os.getenv('GEMINI_API_KEY') else None
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Gemini API Tester...")
    print("📍 Open your browser to: http://localhost:8001")
    print("🔑 Make sure your GEMINI_API_KEY is set in the .env file")
    
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
