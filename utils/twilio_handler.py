"""
Simplified Twilio Business Manager with clear flow and robust error handling.
This implementation focuses on the core functionality:
1. Map business phone numbers to Twilio accounts
2. Provide the right Twilio client for each business
3. Handle call forwarding with the appropriate account
"""

import os
import json
from typing import Dict, Optional, List
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from loguru import logger

# Load environment variables
load_dotenv()

class TwilioBusinessManager:
    """Manager for handling Twilio accounts mapped to business phone numbers."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the business-to-account mapping.
        
        Args:
            config_path: Optional path to JSON configuration file for business-to-account mapping
        """
        self.accounts = {}  # account_sid -> account_info
        self.clients = {}   # account_sid -> Twilio client
        self.phone_map = {} # twilio_phone -> account_sid
        
        # Initialize from config file (if provided)
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)
        else:
            # Fall back to environment variables
            self._initialize_from_env()
            
        logger.info(f"Initialized Twilio Business Manager with {len(self.accounts)} accounts and {len(self.phone_map)} phone mappings")
    
    def _load_config(self, config_path: str):
        """Load business-to-account mapping from a JSON configuration file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Initialize accounts and clients
            for account_sid, account_info in config.get("accounts", {}).items():
                auth_token = account_info.get("auth_token")
                if not auth_token:
                    logger.warning(f"Missing auth_token for account {account_sid}, skipping")
                    continue
                
                # Store account info
                self.accounts[account_sid] = {
                    "auth_token": auth_token,
                    "name": account_info.get("name", "Unknown Business"),
                }
                
                # Create Twilio client
                try:
                    self.clients[account_sid] = Client(account_sid, auth_token)
                    logger.info(f"Created Twilio client for account {account_sid[:8]}...")
                except Exception as e:
                    logger.error(f"Failed to create Twilio client for account {account_sid[:8]}: {str(e)}")
                    continue
                
                # Map phone numbers to this account
                for phone in account_info.get("phone_numbers", []):
                    normalized_phone = self._normalize_phone(phone)
                    self.phone_map[normalized_phone] = account_sid
                    logger.debug(f"Mapped phone {normalized_phone} to account {account_sid[:8]}...")
                    
                logger.info(f"Loaded account {account_sid[:8]}... with {len(account_info.get('phone_numbers', []))} phone numbers")
                
        except Exception as e:
            logger.error(f"Error loading Twilio config from {config_path}: {str(e)}")
    
    def _initialize_from_env(self):
        """Initialize accounts from environment variables for backward compatibility."""
        
        # First, look for a JSON-encoded mapping
        business_mapping = os.getenv("TWILIO_BUSINESS_MAPPING")
        if business_mapping:
            try:
                mapping = json.loads(business_mapping)
                for phone, account_info in mapping.items():
                    account_sid = account_info.get("account_sid")
                    auth_token = account_info.get("auth_token")
                    name = account_info.get("name", "Unknown Business")
                    
                    if not account_sid or not auth_token:
                        logger.warning(f"Missing credentials for {phone}, skipping")
                        continue
                    
                    normalized_phone = self._normalize_phone(phone)
                    
                    # Add to accounts if not already there
                    if account_sid not in self.accounts:
                        self.accounts[account_sid] = {
                            "auth_token": auth_token,
                            "name": name
                        }
                        try:
                            self.clients[account_sid] = Client(account_sid, auth_token)
                            logger.info(f"Created Twilio client for account {account_sid[:8]}...")
                        except Exception as e:
                            logger.error(f"Failed to create Twilio client for account {account_sid[:8]}: {str(e)}")
                            continue
                    
                    # Map phone to account
                    self.phone_map[normalized_phone] = account_sid
                    logger.debug(f"Mapped phone {normalized_phone} to account {account_sid[:8]}...")
                
                logger.info(f"Loaded {len(mapping)} phone-to-account mappings from TWILIO_BUSINESS_MAPPING")
                return
            
            except json.JSONDecodeError:
                logger.error("Failed to parse TWILIO_BUSINESS_MAPPING as JSON, falling back to legacy mode")
        
        # Legacy method: Look for individual account variables
        primary_sid = os.getenv("TWILIO_ACCOUNT_SID")
        primary_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        if primary_sid and primary_token:
            self.accounts[primary_sid] = {
                "auth_token": primary_token,
                "name": "Primary Account"
            }
            try:
                self.clients[primary_sid] = Client(primary_sid, primary_token)
                logger.info(f"Created Twilio client for primary account {primary_sid[:8]}...")
            except Exception as e:
                logger.error(f"Failed to create Twilio client for primary account: {str(e)}")
            
            # Look for phone mappings for primary account
            primary_phones = os.getenv("TWILIO_PRIMARY_PHONES", "")
            if primary_phones:
                phones = [p.strip() for p in primary_phones.split(",")]
                for phone in phones:
                    if phone:
                        normalized_phone = self._normalize_phone(phone)
                        self.phone_map[normalized_phone] = primary_sid
                        logger.debug(f"Mapped phone {normalized_phone} to primary account")
                logger.info(f"Mapped {len(phones)} phone numbers to primary account")
        
        # Look for any number of secondary accounts
        i = 1
        while True:
            account_sid = os.getenv(f"TWILIO_ACCOUNT_SID_{i}")
            auth_token = os.getenv(f"TWILIO_AUTH_TOKEN_{i}")
            
            if not account_sid or not auth_token:
                break  # No more accounts
            
            self.accounts[account_sid] = {
                "auth_token": auth_token,
                "name": f"Secondary Account {i}"
            }
            
            try:
                self.clients[account_sid] = Client(account_sid, auth_token)
                logger.info(f"Created Twilio client for secondary account {i}: {account_sid[:8]}...")
            except Exception as e:
                logger.error(f"Failed to create Twilio client for secondary account {i}: {str(e)}")
                i += 1
                continue
            
            # Look for phone mappings for this account
            account_phones = os.getenv(f"TWILIO_ACCOUNT_{i}_PHONES", "")
            if account_phones:
                phones = [p.strip() for p in account_phones.split(",")]
                for phone in phones:
                    if phone:
                        normalized_phone = self._normalize_phone(phone)
                        self.phone_map[normalized_phone] = account_sid
                        logger.debug(f"Mapped phone {normalized_phone} to account {i}")
                logger.info(f"Mapped {len(phones)} phone numbers to account {i}")
            
            i += 1
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number format for consistent lookups."""
        # Remove all non-digit characters
        digits_only = ''.join(filter(str.isdigit, phone))
        
        # Ensure it has country code (default to +1 if missing)
        if len(digits_only) == 10:  # US number without country code
            return f"+1{digits_only}"
        elif digits_only.startswith("1") and len(digits_only) == 11:  # US number with country code
            return f"+{digits_only}"
        else:
            return f"+{digits_only}"
    
    def get_client_for_phone(self, phone: str) -> Optional[Client]:
        """
        Get Twilio client for a specific phone number.
        
        Args:
            phone: The Twilio phone number
            
        Returns:
            Twilio client for the account that owns this phone number, or None if not found
        """
        if not phone:
            logger.warning("Empty phone number provided to get_client_for_phone")
            return self._get_default_client()
            
        normalized_phone = self._normalize_phone(phone)
        account_sid = self.phone_map.get(normalized_phone)
        
        if account_sid and account_sid in self.clients:
            logger.info(f"Using Twilio client for {normalized_phone} from account {account_sid[:8]}...")
            return self.clients[account_sid]
        
        logger.warning(f"No account found for phone number {phone} (normalized: {normalized_phone})")
        return self._get_default_client()
    
    def _get_default_client(self) -> Optional[Client]:
        """Get a default client when no specific match is found."""
        # Return the first client as fallback if we have any
        if self.clients:
            first_sid = next(iter(self.clients))
            logger.warning(f"Falling back to default account {first_sid[:8]}...")
            return self.clients[first_sid]
        return None
    
    def get_account_for_phone(self, phone: str) -> Optional[str]:
        """
        Get the account SID for a given phone number.
        
        Args:
            phone: The Twilio phone number
            
        Returns:
            Account SID or None if not found
        """
        if not phone:
            logger.warning("Empty phone number provided to get_account_for_phone")
            return None
            
        normalized_phone = self._normalize_phone(phone)
        account_sid = self.phone_map.get(normalized_phone)
        
        if account_sid:
            logger.info(f"Found account {account_sid[:8]}... for phone {normalized_phone}")
            
        return account_sid
    
    def forward_call(self, call_sid: str, sip_uri: str, business_phone: Optional[str] = None) -> bool:
        """
        Forward a call to a SIP URI using the appropriate Twilio account.
        
        Args:
            call_sid: The Twilio call SID
            sip_uri: The SIP URI to forward to
            business_phone: Optional business phone number to determine account
            
        Returns:
            True if successful, False otherwise
        """
        # First, try using business_phone to get the client if provided
        client = None
        if business_phone:
            client = self.get_client_for_phone(business_phone)
            if client:
                logger.info(f"Using client for business phone {business_phone} to forward call {call_sid}")
        
        # If we couldn't get a client from the business phone or none was provided,
        # try finding a client that can handle this call
        if not client:
            for account_sid, account_client in self.clients.items():
                try:
                    # Check if this client can access the call
                    call = account_client.calls(call_sid).fetch()
                    # If we get here, the client can access the call
                    client = account_client
                    logger.info(f"Found client for call {call_sid} in account {account_sid[:8]}...")
                    break
                except Exception:
                    # Try the next account
                    continue
        
        # If we still don't have a client, use the default
        if not client:
            client = self._get_default_client()
            if not client:
                logger.error(f"No Twilio client available to forward call {call_sid}")
                return False
            logger.warning(f"Using default client to forward call {call_sid}")
        
        # Forward the call using the selected client
        try:
            client.calls(call_sid).update(
                twiml=f"<Response><Dial><Sip>{sip_uri}</Sip></Dial></Response>"
            )
            logger.info(f"Call {call_sid} forwarded successfully to {sip_uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to forward call {call_sid}: {str(e)}")
            return False
    
    def get_business_name(self, phone: str) -> str:
        """
        Get business name for a phone number from the configuration.
        
        Args:
            phone: The business phone number
            
        Returns:
            Business name or "Our Business" if not found
        """
        if not phone:
            return "Our Business"
            
        normalized_phone = self._normalize_phone(phone)
        account_sid = self.phone_map.get(normalized_phone)
        
        if account_sid and account_sid in self.accounts:
            return self.accounts[account_sid].get("name", "Our Business")
        
        return "Our Business"
    
    def get_all_accounts(self) -> Dict:
        """Get all configured Twilio accounts (masked for security)."""
        return {
            sid[:8] + "..." + sid[-4:]: {
                "name": info["name"],
                "phone_count": sum(1 for p, a in self.phone_map.items() if a == sid)
            }
            for sid, info in self.accounts.items()
        }
    
    def get_all_phone_mappings(self) -> Dict:
        """Get all phone-to-account mappings (masked for security)."""
        return {
            phone: account_sid[:8] + "..." + account_sid[-4:] 
            for phone, account_sid in self.phone_map.items()
        }


# Singleton instance
_twilio_manager = None

def get_twilio_manager() -> TwilioBusinessManager:
    """Get the singleton TwilioBusinessManager instance."""
    global _twilio_manager
    
    if _twilio_manager is None:
        config_path = os.getenv("TWILIO_CONFIG_PATH")
        _twilio_manager = TwilioBusinessManager(config_path)
    
    return _twilio_manager


# Helper functions for direct use

def forward_call(call_sid: str, sip_uri: str, business_phone: Optional[str] = None) -> bool:
    """Forward a call using the appropriate Twilio account."""
    manager = get_twilio_manager()
    return manager.forward_call(call_sid, sip_uri, business_phone)

def get_client_for_phone(phone: str) -> Optional[Client]:
    """Get the Twilio client for a specific phone number."""
    manager = get_twilio_manager()
    return manager.get_client_for_phone(phone)

def get_business_name(phone: str) -> str:
    """Get business name for a phone number from the configuration."""
    manager = get_twilio_manager()
    return manager.get_business_name(phone)