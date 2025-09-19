#!/usr/bin/env python3
"""
Text-to-Speech API Test Example

This script demonstrates how to use the new text-to-speech API endpoint.
"""

import requests
import json
import os

# Configuration
API_BASE_URL = "http://localhost:5000"
TTS_ENDPOINT = f"{API_BASE_URL}/api/text-to-speech/"

def test_text_to_speech():
    """Test the text-to-speech API endpoint"""
    
    print("🔊 Testing Text-to-Speech API")
    print("=" * 50)
    
    # Test data
    test_data = {
        "user_id": "test_user_123",
        "character_id": "test_character_456", 
        "text": "Hello! This is a test of the text-to-speech service. How does it sound?",
        "voice_name": "en-IN-AartiIndicNeural",  # Optional, defaults to this
        "language": "en-IN"  # Optional, defaults to this
    }
    
    print(f"📝 Request Data:")
    print(json.dumps(test_data, indent=2))
    print()
    
    try:
        print("📡 Sending request to API...")
        response = requests.post(
            TTS_ENDPOINT,
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=60  # 60 second timeout for speech synthesis
        )
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success! Text-to-speech conversion completed.")
            print(f"📄 Response:")
            print(json.dumps(result, indent=2))
            print()
            print(f"🔗 Audio URL: {result.get('audio_url')}")
            print(f"⏱️  Total Time: {result.get('total_time_seconds')}s")
            print(f"🎤 Voice Used: {result.get('voice_name')}")
            print(f"📊 Audio Size: {result.get('audio_size_bytes')} bytes")
            
        else:
            print("❌ Request failed!")
            print(f"📄 Error Response:")
            try:
                error_data = response.json()
                print(json.dumps(error_data, indent=2))
            except:
                print(response.text)
                
    except requests.exceptions.Timeout:
        print("⏰ Request timed out - this can happen with long text")
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure the server is running")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def test_form_data_request():
    """Test using form data instead of JSON"""
    
    print("\n🔊 Testing Text-to-Speech API with Form Data")
    print("=" * 50)
    
    # Test data as form data
    form_data = {
        "user_id": "test_user_789",
        "character_id": "test_character_101",
        "text": "This is a form data test. The API should handle both JSON and form data.",
        "voice_name": "en-IN-AartiIndicNeural",
        "language": "en-IN"
    }
    
    print(f"📝 Form Data:")
    for key, value in form_data.items():
        print(f"  {key}: {value}")
    print()
    
    try:
        print("📡 Sending form data request...")
        response = requests.post(
            TTS_ENDPOINT,
            data=form_data,  # Using data instead of json
            timeout=60
        )
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success! Form data request worked.")
            print(f"🔗 Audio URL: {result.get('audio_url')}")
            print(f"⏱️  Total Time: {result.get('total_time_seconds')}s")
        else:
            print("❌ Form data request failed!")
            try:
                error_data = response.json()
                print(json.dumps(error_data, indent=2))
            except:
                print(response.text)
                
    except Exception as e:
        print(f"❌ Form data request error: {e}")

def test_different_voices():
    """Test different voice options"""
    
    print("\n🎤 Testing Different Voice Options")
    print("=" * 50)
    
    # Different voice options for Indian English
    voices = [
        "en-IN-AartiNeural",
        "en-IN-AartiIndicNeural", 
        "en-IN-AnanyaNeural",
        "en-IN-RaviNeural"
    ]
    
    base_data = {
        "user_id": "voice_test_user",
        "character_id": "voice_test_character",
        "text": "Testing different voice options for text-to-speech.",
        "language": "en-IN"
    }
    
    for voice in voices:
        print(f"🎤 Testing voice: {voice}")
        test_data = base_data.copy()
        test_data["voice_name"] = voice
        
        try:
            response = requests.post(
                TTS_ENDPOINT,
                json=test_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✅ Success! Audio URL: {result.get('audio_url')}")
            else:
                print(f"  ❌ Failed with status: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()

if __name__ == "__main__":
    print("🚀 Starting Text-to-Speech API Tests")
    print("Make sure your Flask server is running on localhost:5000")
    print()
    
    # Run tests
    test_text_to_speech()
    test_form_data_request() 
    test_different_voices()
    
    print("\n🎯 Test completed!")
    print("\n📋 Usage Summary:")
    print("- POST /api/text-to-speech/")
    print("- Required: user_id, character_id, text")
    print("- Optional: voice_name, language")
    print("- Supports both JSON and form data")
    print("- Returns: audio_url, synthesis details")
    print("- Audio files stored in S3 speech-audio/ folder")
