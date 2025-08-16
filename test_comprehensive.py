#!/usr/bin/env python3
"""
Comprehensive test script for the FastAPI application
"""

import requests
import json
import os
import time

def test_health_check():
    """Test the health check endpoint"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        if response.status_code == 200:
            print("✓ Health check passed")
            print(f"  Response: {response.json()}")
            return True
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: ./start.sh or uvicorn main:app --reload")
        return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_csv_analysis():
    """Test the API with CSV analysis"""
    print("\n🧪 Testing CSV Analysis...")
    
    # Read questions file
    with open('csv_questions.txt', 'r') as f:
        questions_content = f.read()
    
    # Read CSV file
    with open('sample_movies.csv', 'rb') as f:
        csv_content = f.read()
    
    files = {
        'questions.txt': ('questions.txt', questions_content, 'text/plain'),
        'sample_movies.csv': ('sample_movies.csv', csv_content, 'text/csv')
    }
    
    print("📤 Sending CSV analysis request...")
    try:
        response = requests.post("http://localhost:8000/api/", files=files, timeout=60)
        
        if response.status_code == 200:
            print("✓ CSV analysis successful!")
            result = response.json()
            print("📊 Results:")
            for i, answer in enumerate(result, 1):
                if isinstance(answer, str) and answer.startswith("data:image/png;base64,"):
                    print(f"  Question {i}: [Base64 Image Data - {len(answer)} chars]")
                else:
                    print(f"  Question {i}: {answer}")
            return True
        else:
            print(f"❌ CSV analysis failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (this is normal for complex analysis)")
        return False
    except Exception as e:
        print(f"❌ CSV analysis error: {e}")
        return False

def test_simple_questions():
    """Test with simple questions that don't require external data"""
    print("\n🧪 Testing Simple Questions...")
    
    simple_questions = """Answer these simple questions.

QUESTIONS:
1. What is 2 + 2?
2. What is the capital of France?
3. Calculate the square root of 16.
"""
    
    files = {
        'questions.txt': ('questions.txt', simple_questions, 'text/plain')
    }
    
    print("📤 Sending simple questions...")
    try:
        response = requests.post("http://localhost:8000/api/", files=files, timeout=30)
        
        if response.status_code == 200:
            print("✓ Simple questions successful!")
            result = response.json()
            print("📊 Results:")
            for i, answer in enumerate(result, 1):
                print(f"  Question {i}: {answer}")
            return True
        else:
            print(f"❌ Simple questions failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Simple questions error: {e}")
        return False

def test_missing_questions_file():
    """Test error handling when questions.txt is missing"""
    print("\n🧪 Testing Error Handling (Missing questions.txt)...")
    
    files = {
        'sample.csv': ('sample.csv', 'data,value\n1,2\n', 'text/csv')
    }
    
    try:
        response = requests.post("http://localhost:8000/api/", files=files, timeout=10)
        
        if response.status_code == 400:
            print("✓ Error handling works correctly (400 status for missing questions.txt)")
            return True
        else:
            print(f"❌ Expected 400 status, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 FastAPI Question Answering API Test Suite")
    print("=" * 50)
    
    # Test health check first
    if not test_health_check():
        return
    
    # Test error handling
    test_missing_questions_file()
    
    # Test simple questions
    test_simple_questions()
    
    # Test CSV analysis
    test_csv_analysis()
    
    print("\n" + "=" * 50)
    print("🏁 Test suite completed!")
    print("\n💡 Note: Some tests may fail if GEMINI_API_KEY is not set correctly")
    print("💡 Complex analysis tests may take 30-60 seconds to complete")

if __name__ == "__main__":
    main()
