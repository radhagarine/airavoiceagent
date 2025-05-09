"""Helper functions for interacting with Supabase."""

import os
import logging
import re
from typing import Optional, Dict

from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

def get_supabase_client() -> Client:
    """Get a Supabase client instance.
    
    Returns:
        A configured Supabase client
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    # Log partial key for debugging
    logger.info(f"Using Supabase URL: {url}")
    logger.info(f"Using Supabase Key: {key[:5]}...{key[-5:] if len(key) > 10 else ''}")
    
    # Create and return the client
    return create_client(url, key)

def normalize_phone_number(phone_number: str, strip_country_code: bool = False) -> str:
    """Normalize a phone number by removing all non-digit characters.
    
    Args:
        phone_number: The phone number to normalize
        strip_country_code: Whether to strip the leading '1' (US country code)
        
    Returns:
        The normalized phone number with only digits
    """
    # Keep only digits
    digits_only = re.sub(r'\D', '', phone_number)
    
    # Optionally strip country code if it's a US number
    if strip_country_code and digits_only.startswith('1') and len(digits_only) > 10:
        return digits_only[1:]  # Remove the leading '1'
    
    return digits_only

def get_business_by_phone(phone_number: str) -> Optional[dict]:
    """Get the business details associated with a phone number.
    
    Args:
        phone_number: The phone number to look up
        
    Returns:
        Dictionary with business details if found, None otherwise
    """
    try:
        print(f"DEBUGGER: get_business_by_phone called with: {phone_number}")
        
        supabase = get_supabase_client()
        
        # Try multiple normalizations
        normalized_phone = normalize_phone_number(phone_number)
        normalized_phone_no_country = normalize_phone_number(phone_number, strip_country_code=True)
        
        print(f"DEBUGGER: Normalized formats: with country code '{normalized_phone}', without country code '{normalized_phone_no_country}'")
        logger.info(f"Looking up business for phone: '{phone_number}'")
        
        # First try a direct match of the exact phone format
        # For '+' characters, use Postgres LIKE operator to avoid URL encoding issues
        if '+' in phone_number:
            # Need to escape special characters for LIKE
            like_phone = phone_number.replace('+', '\\+').replace('(', '\\(').replace(')', '\\)')
            logger.info(f"Phone contains special chars, using LIKE with: '{like_phone}'")
            # Use ILIKE for case-insensitive matching
            response = supabase.table("business_v2").select("id,name,phone").ilike("phone", like_phone).execute()
            if response.data and len(response.data) > 0:
                business = response.data[0]
                logger.info(f"Found business with ILIKE: {business}")
                return business
                
            # If that fails, try direct comparison which compares the raw string but will URL-encode
            logger.info(f"ILIKE failed, trying direct eq match with: '{phone_number}'")
            response = supabase.table("business_v2").select("id,name,phone").eq("phone", phone_number).execute()
            if response.data and len(response.data) > 0:
                business = response.data[0]
                logger.info(f"Found business with eq: {business}")
                return business
        else:
            # No special characters, use direct equality
            logger.info(f"Trying exact match with: '{phone_number}'")
            response = supabase.table("business_v2").select("id,name,phone").eq("phone", phone_number).execute()
            if response.data and len(response.data) > 0:
                business = response.data[0]
                logger.info(f"Found business with exact match: {business}")
                return business
            
        # Try with other formats
        formats_to_try = [
            normalized_phone,  # Digits only with country code (e.g., 18554494055)
            normalized_phone_no_country,  # Digits only without country code (e.g., 8554494055)
        ]
        
        # If there's a + (e.g., "+18554494055"), also try without it
        # (we already tried with the + directly above)
        if phone_number.startswith('+'):
            formats_to_try.append(phone_number[1:])  # Without + (e.g., 18554494055)
        
        # Try equality matches with the other formats
        for fmt in formats_to_try:
            logger.info(f"Trying format: '{fmt}'")
            response = supabase.table("business_v2").select("id,name,phone").eq("phone", fmt).execute()
            
            if response.data and len(response.data) > 0:
                business = response.data[0]
                logger.info(f"Found business with format '{fmt}': {business}")
                return business
        
        # If all else fails, get all records and compare manually
        logger.info("All Supabase queries failed, retrieving all businesses to compare manually")
        all_response = supabase.table("business_v2").select("id,name,phone").execute()
        
        if all_response.data:
            logger.info(f"Retrieved {len(all_response.data)} businesses")
            
            for business in all_response.data:
                db_phone = business.get("phone", "")
                logger.info(f"Checking business: {business}")
                
                # Check exact match
                if db_phone == phone_number:
                    logger.info(f"Direct string comparison match: {db_phone} == {phone_number}")
                    return business
                
                # Check normalized versions
                db_normalized = normalize_phone_number(db_phone)
                
                if db_normalized == normalized_phone or db_normalized == normalized_phone_no_country:
                    logger.info(f"Normalized match: {db_normalized} == {normalized_phone} or {normalized_phone_no_country}")
                    return business
                
                # Check without + if DB phone has it
                if db_phone.startswith('+') and db_phone[1:] == phone_number:
                    logger.info(f"Match after removing +: {db_phone[1:]} == {phone_number}")
                    return business
                
                # Check if phone_number without + matches DB phone
                if phone_number.startswith('+') and phone_number[1:] == db_phone:
                    logger.info(f"Match after removing + from query: {phone_number[1:]} == {db_phone}")
                    return business
        
        logger.warning(f"No business found for phone number: '{phone_number}' after exhaustive matching")
        return None
            
    except Exception as e:
        logger.error(f"Error looking up business by phone number: {str(e)}")
        return None

def get_business_id_by_phone(phone_number: str) -> Optional[str]:
    """Get the business ID associated with a phone number.
    
    Args:
        phone_number: The phone number to look up
        
    Returns:
        The business ID if found, None otherwise
    """
    business = get_business_by_phone(phone_number)
    if business:
        return business.get("id")
    return None