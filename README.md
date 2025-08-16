# FastAPI Question Answering Application

source /workspaces/fluffy-memory/.venv/bin/activate

This FastAPI application processes multipart/form-data requests containing a `questions.txt` file and optional data files (CSV, Excel, images, databases) to answer questions using a LangChain Agent powered by Google's Gemini LLM.

## Features

- **Web Scraping**: Extract data from websites using requests and BeautifulSoup
- **Data Analysis**: Load and analyze CSV/Excel files with Pandas
- **SQL Queries**: Execute SQL queries on uploaded databases or create in-memory SQLite databases
- **Python Code Execution**: Run custom Python code for complex data processing
- **Plotting**: Generate matplotlib plots and return as base64 data URIs
- **Gemini Integration**: Uses Google's Gemini Pro model via LangChain

## Installation

1. Clone or create the project directory
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your Gemini API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your actual Gemini API key
   ```

## Usage

### Start the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API Endpoint

**POST** `/api/`

- **Content-Type**: `multipart/form-data`
- **Required**: `questions.txt` file
- **Optional**: Additional files (CSV, Excel, PNG, JPG, DB, etc.)

### Example Request

```bash
curl "http://localhost:8000/api/" \
  -F "files=@example_questions.txt;filename=questions.txt" \
  -F "files=@data.csv" \
  -F "files=@image.png"
```

### Questions File Format

The `questions.txt` file should contain:

1. **Instructions** (optional): Natural language instructions for data processing
2. **QUESTIONS:** section: Numbered list of questions

Example:
```
Scrape the list of highest grossing films from Wikipedia. It is at the URL:
https://en.wikipedia.org/wiki/List_of_highest-grossing_films

Answer the following questions and respond with a JSON array of strings containing the answer.

QUESTIONS:
1. How many $2 bn movies were released before 2000?
2. Which is the earliest film that grossed over $1.5 bn?
3. What's the correlation between the Rank and Peak?
4. Draw a scatterplot of Rank and Peak along with a dotted red regression line through it.
```

### Response Format

The API returns a JSON array with answers in the same order as the questions:

```json
[1, "Titanic", 0.485782, "data:image/png;base64,iVBORw0KG..."]
```

## Available Tools

The LangChain Agent has access to these tools:

1. **Web Scraper**: Scrape content from URLs
2. **CSV/Excel Loader**: Load and preview data files
3. **Pandas Operations**: Perform data analysis with pandas
4. **SQL Query Tool**: Execute SQL queries on databases
5. **Python REPL**: Execute custom Python code
6. **Matplotlib Plotter**: Create plots and return as base64 data URIs

## Environment Variables

- `GEMINI_API_KEY`: Your Google Gemini API key (required)

## Testing

Run the test script:
```bash
python test_api.py
```

This will test the API with the example questions file.

## File Support

- **CSV/Excel**: Automatically loaded into pandas DataFrames
- **Databases**: SQLite, DB files for SQL queries
- **Images**: PNG, JPG files available for processing
- **Text**: Any text-based files for analysis

## Error Handling

- Returns 400 if `questions.txt` is missing
- Returns 500 for processing errors
- Validates JSON output before returning
- Automatic cleanup of temporary files

## Limitations

- Plot images are limited to 100KB in base64 format
- Web scraping limited to 10K characters per page
- SQL queries timeout after reasonable limits
- Temporary files are automatically cleaned up after each request

## Architecture

The application uses:
- **FastAPI** for the web API framework
- **LangChain** for agent orchestration and tool management
- **Google Gemini Pro** as the reasoning LLM
- **Pandas** for data manipulation
- **Matplotlib** for plotting
- **SQLite** for database operations
- **BeautifulSoup** for web scraping
