#!/usr/bin/env python
"""
Debug script for Twilio configuration.
This helps identify issues with authentication.
"""

import os
import sys
import json
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Load environment variables
load_dotenv()

def print_separator(title=""):
    width = 60
    if title:
        padding = (width - len(title) - 2) // 2
        print("\n" + "=" * padding + f" {title} " + "=" * padding)
    else:
        print("\n" + "=" * width)

def mask_token(token):
    """Mask the auth token for display, showing only first/last 5 chars."""
    if not token:
        return "None"
    if len(token) <= 10:
        return "***" # Too short to partially show
    return token[:5] + "..." + token[-5:]

def test_direct_authentication():
    """Test direct authentication with Twilio using environment variables."""
    print_separator("Direct Authentication Test")
    
    # Check primary account
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    print(f"Primary Account SID: {account_sid}")
    print(f"Auth Token (masked): {mask_token(auth_token)}")
    
    if account_sid and auth_token:
        try:
            client = Client(account_sid, auth_token)
            account = client.api.accounts(account_sid).fetch()
            print(f"✅ Direct authentication successful!")
            print(f"   Account Status: {account.status}")
            print(f"   Account Type: {account.type}")
        except Exception as e:
            print(f"❌ Direct authentication failed: {str(e)}")
    else:
        print("❌ Missing primary credentials in environment variables")

def check_config_file():
    """Check the Twilio config file if it exists."""
    print_separator("Configuration File Check")
    
    config_path = os.getenv("TWILIO_CONFIG_PATH")
    if not config_path:
        print("❌ TWILIO_CONFIG_PATH not set in environment")
        return
    
    print(f"Looking for config file at: {config_path}")
    
    if not os.path.exists(config_path):
        print(f"❌ Config file not found at {config_path}")
        return
    
    print(f"✅ Config file exists")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        print(f"✅ Config file parsed successfully")
        
        accounts = config.get("accounts", {})
        print(f"Found {len(accounts)} accounts in config")
        
        for account_sid, account_info in accounts.items():
            print(f"\nAccount: {account_sid}")
            
            auth_token = account_info.get("auth_token")
            name = account_info.get("name", "Unnamed")
            phones = account_info.get("phone_numbers", [])
            
            print(f"  Name: {name}")
            print(f"  Auth Token (masked): {mask_token(auth_token)}")
            print(f"  Phone Numbers: {', '.join(phones) if phones else 'None'}")
            
            # Test this account
            if auth_token:
                try:
                    client = Client(account_sid, auth_token)
                    account = client.api.accounts(account_sid).fetch()
                    print(f"  ✅ Authentication successful!")
                    print(f"     Account Status: {account.status}")
                    print(f"     Account Type: {account.type}")
                except Exception as e:
                    print(f"  ❌ Authentication failed: {str(e)}")
            else:
                print("  ❌ Missing auth token for this account")
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse config file: {str(e)}")
    except Exception as e:
        print(f"❌ Error checking config file: {str(e)}")

def check_phone_number(phone):
    """Test authenticating to access a specific phone number."""
    print_separator(f"Testing Phone Number: {phone}")
    
    # First try direct auth from env vars
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if account_sid and auth_token:
        try:
            client = Client(account_sid, auth_token)
            incoming_numbers = client.incoming_phone_numbers.list(phone_number=phone)
            
            if incoming_numbers:
                print(f"✅ Found phone number {phone} in primary account")
                for num in incoming_numbers:
                    print(f"   Friendly Name: {num.friendly_name}")
                    print(f"   SID: {num.sid}")
                return
            else:
                print(f"ℹ️  Phone number {phone} not found in primary account")
        except Exception as e:
            print(f"ℹ️  Error checking primary account: {str(e)}")
    
    # Next, try checking the config file
    config_path = os.getenv("TWILIO_CONFIG_PATH")
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Search through accounts for this phone number
            for account_sid, account_info in config.get("accounts", {}).items():
                phones = account_info.get("phone_numbers", [])
                
                if phone in phones:
                    print(f"✅ Found phone number in config file for account: {account_sid}")
                    print(f"   Business Name: {account_info.get('name', 'Unnamed')}")
                    
                    # Try to verify with API
                    auth_token = account_info.get("auth_token")
                    if auth_token:
                        try:
                            client = Client(account_sid, auth_token)
                            incoming_numbers = client.incoming_phone_numbers.list(phone_number=phone)
                            
                            if incoming_numbers:
                                print(f"✅ Verified phone number exists in this Twilio account")
                                return
                            else:
                                print(f"❌ Phone number is in config but NOT found in the Twilio account")
                        except Exception as e:
                            print(f"❌ Could not verify phone with API: {str(e)}")
                    return
        except Exception as e:
            print(f"Error checking config file: {str(e)}")
    
    print(f"❌ Phone number {phone} not found in any configuration")

def main():
    print("🔍 TWILIO CONFIGURATION DEBUG 🔍")
    print("===============================")
    
    # Check if a phone number was provided
    if len(sys.argv) > 1:
        check_phone_number(sys.argv[1])
    else:
        # Test direct auth first
        test_direct_authentication()
        
        # Then check config file
        check_config_file()
        
        print_separator("Debug Complete")
        print("To test a specific phone number:")
        print(f"   {sys.argv[0]} +14155551234")

if __name__ == "__main__":
    main()