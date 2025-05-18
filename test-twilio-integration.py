#!/usr/bin/env python
"""
Quick test script for the simplified business-driven Twilio integration.
Use this to verify your implementation.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 10} {title} {'=' * 10}")

def print_success(message):
    """Print a success message."""
    print(f"✅ {message}")

def print_error(message):
    """Print an error message."""
    print(f"❌ {message}")

def print_warning(message):
    """Print a warning message."""
    print(f"⚠️ {message}")

def print_info(message):
    """Print an info message."""
    print(f"ℹ️ {message}")

def test_setup():
    """Test if all required files and environment variables are set up."""
    print_section("Testing Setup")
    
    # Check for twilio_handler.py
    if not os.path.exists("utils/twilio_handler.py"):
        print_error("utils/twilio_handler.py not found")
        return False
    
    # Check for config file path
    config_path = os.getenv("TWILIO_CONFIG_PATH")
    if not config_path:
        print_warning("TWILIO_CONFIG_PATH not set in environment")
        print_info("Will look for other Twilio configuration methods")
    else:
        if os.path.exists(config_path):
            print_success(f"Twilio configuration file found at {config_path}")
        else:
            print_error(f"Twilio configuration file not found at {config_path}")
            return False
    
    # Check for other environment variables
    if os.getenv("TWILIO_BUSINESS_MAPPING"):
        print_success("TWILIO_BUSINESS_MAPPING found in environment")
    elif os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"):
        print_success("Found TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in environment")
    elif not config_path:
        print_error("No Twilio configuration found")
        return False
    
    return True

def test_imports():
    """Test importing the Twilio handler."""
    print_section("Testing Imports")
    
    try:
        sys.path.append('.')
        from utils.twilio_handler import get_twilio_manager, forward_call, get_client_for_phone, get_business_name
        print_success("Successfully imported Twilio handler functions")
        return True
    except ImportError as e:
        print_error(f"Error importing Twilio handler: {str(e)}")
        return False

def test_manager():
    """Test the Twilio manager."""
    print_section("Testing Twilio Manager")
    
    try:
        from utils.twilio_handler import get_twilio_manager
        
        manager = get_twilio_manager()
        print_success("Successfully created Twilio manager")
        
        # Check accounts
        accounts = manager.accounts
        if accounts:
            print_success(f"Found {len(accounts)} Twilio accounts")
            for sid, info in accounts.items():
                print_info(f"Account: {sid[:8]}... - {info.get('name', 'Unnamed')}")
        else:
            print_error("No Twilio accounts found")
            return False
        
        # Check phone mappings
        phone_map = manager.phone_map
        if phone_map:
            print_success(f"Found {len(phone_map)} phone-to-account mappings")
            
            # Show a few examples
            examples = list(phone_map.items())[:3]
            for phone, account_sid in examples:
                account_name = accounts[account_sid].get('name', 'Unnamed')
                print_info(f"Phone: {phone} => Account: {account_sid[:8]}... ({account_name})")
        else:
            print_warning("No phone-to-account mappings found")
        
        return True
    except Exception as e:
        print_error(f"Error testing Twilio manager: {str(e)}")
        return False

def test_specific_phone(phone_number):
    """Test a specific phone number."""
    print_section(f"Testing Phone Number: {phone_number}")
    
    try:
        from utils.twilio_handler import get_twilio_manager, get_client_for_phone, get_business_name
        
        manager = get_twilio_manager()
        
        # Check if phone is mapped
        account_sid = manager.get_account_for_phone(phone_number)
        if account_sid:
            print_success(f"Phone {phone_number} is mapped to account {account_sid[:8]}...")
            
            # Get business name
            business_name = get_business_name(phone_number)
            print_success(f"Business name: {business_name}")
            
            # Try to get client
            client = get_client_for_phone(phone_number)
            if client:
                print_success("Successfully created Twilio client for this phone number")
                return True
            else:
                print_error("Failed to create Twilio client for this phone number")
                return False
        else:
            print_warning(f"Phone {phone_number} is not mapped to any account")
            print_info("Available phone mappings:")
            for i, (phone, account) in enumerate(manager.phone_map.items()[:5]):
                print_info(f"  {phone} => {account[:8]}...")
                if i >= 4 and len(manager.phone_map) > 5:
                    print_info(f"  ... and {len(manager.phone_map) - 5} more")
                    break
            return False
    except Exception as e:
        print_error(f"Error testing phone number: {str(e)}")
        return False

def main():
    print("🔍 SIMPLIFIED TWILIO INTEGRATION TEST 🔍")
    print("========================================")
    
    # Run tests
    if not test_setup():
        print_error("Setup test failed")
        return 1
    
    if not test_imports():
        print_error("Import test failed")
        return 1
    
    if not test_manager():
        print_error("Manager test failed")
        return 1
    
    # Test specific phone if provided
    if len(sys.argv) > 1:
        phone_number = sys.argv[1]
        test_specific_phone(phone_number)
    else:
        print_info("\nTo test a specific phone number, run:")
        print_info(f"  {sys.argv[0]} +14155551234")
    
    print("\n✨ All tests passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())