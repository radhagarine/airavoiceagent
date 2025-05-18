#!/usr/bin/env python
"""
Test script for business-driven Twilio integration.
This script helps verify your business-to-account mappings.
"""

import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import our Twilio handler
try:
    sys.path.append('.')
    from utils.twilio_handler import get_twilio_manager
    HANDLER_AVAILABLE = True
except ImportError:
    HANDLER_AVAILABLE = False
    print("⚠️  Could not import the TwilioBusinessManager - make sure utils/twilio_handler.py exists")
    sys.exit(1)

def print_separator(title=""):
    width = 60
    if title:
        padding = (width - len(title) - 2) // 2
        print("\n" + "=" * padding + f" {title} " + "=" * padding)
    else:
        print("\n" + "=" * width)

def test_business_phone(phone):
    """Test a specific business phone number."""
    print_separator(f"Testing Phone: {phone}")
    
    manager = get_twilio_manager()
    account_sid = manager.get_account_for_phone(phone)
    
    if account_sid:
        print(f"✅ Phone {phone} is mapped to account: {account_sid[:8]}...{account_sid[-4:]}")
        
        # Get business info
        business_name = manager.accounts[account_sid].get('name', 'Unknown Business')
        print(f"📞 Business Name: {business_name}")
        
        # Try to create a client
        client = manager.get_client_for_phone(phone)
        if client:
            print(f"✅ Successfully created Twilio client for this phone number")
            
            # Test if the client works
            try:
                account_info = client.api.accounts(account_sid).fetch()
                print(f"✅ Client authenticated successfully with Twilio API")
                print(f"   Account Status: {account_info.status}")
                print(f"   Account Type: {account_info.type}")
            except Exception as e:
                print(f"❌ Client authentication failed: {str(e)}")
        else:
            print(f"❌ Failed to create Twilio client for this phone")
    else:
        print(f"❌ No account mapping found for phone {phone}")
        
        # Try normalized versions
        normalized = manager._normalize_phone(phone)
        if normalized != phone:
            print(f"ℹ️  Normalized phone: {normalized}")
            print(f"ℹ️  Try adding this normalized version to your configuration")
        
        print("\nℹ️  Available phone mappings:")
        for p, a in manager.phone_map.items():
            print(f"   {p} -> {a[:8]}...{a[-4:]}")

def show_config_stats():
    """Show statistics about the current configuration."""
    print_separator("Configuration Statistics")
    
    manager = get_twilio_manager()
    
    # Account stats
    print(f"🔑 Total Twilio Accounts: {len(manager.accounts)}")
    for sid, info in manager.accounts.items():
        masked_sid = f"{sid[:8]}...{sid[-4:]}"
        name = info.get('name', 'Unnamed Business')
        print(f"   • {masked_sid}: {name}")
    
    # Phone mapping stats
    print(f"\n📱 Total Phone Mappings: {len(manager.phone_map)}")
    
    # Group by account
    phones_by_account = {}
    for phone, account in manager.phone_map.items():
        if account not in phones_by_account:
            phones_by_account[account] = []
        phones_by_account[account].append(phone)
    
    for account, phones in phones_by_account.items():
        masked_account = f"{account[:8]}...{account[-4:]}"
        name = manager.accounts.get(account, {}).get('name', 'Unknown Business')
        print(f"   • {name} ({masked_account}): {len(phones)} phone numbers")
        if len(phones) <= 5:  # Only show if not too many
            for phone in phones:
                print(f"     - {phone}")

def main():
    print("🔍 BUSINESS-DRIVEN TWILIO CONFIGURATION TEST 🔍")
    print("==============================================")
    
    # Check if any arguments were provided
    if len(sys.argv) > 1:
        # Test specific phone number
        test_business_phone(sys.argv[1])
    else:
        # Show general configuration
        manager = get_twilio_manager()
        
        # Show config source
        config_path = os.getenv("TWILIO_CONFIG_PATH")
        if config_path:
            print(f"📄 Using configuration file: {config_path}")
        elif os.getenv("TWILIO_BUSINESS_MAPPING"):
            print("🔤 Using TWILIO_BUSINESS_MAPPING environment variable")
        else:
            print("🔤 Using individual account environment variables")
        
        # Show configuration stats
        show_config_stats()
        
        # Instructions for testing a specific phone
        print("\nℹ️  To test a specific phone number:")
        print(f"   {sys.argv[0]} +14155551234")

if __name__ == "__main__":
    main()