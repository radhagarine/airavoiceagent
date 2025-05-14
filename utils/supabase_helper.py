"""Helper functions for interacting with Supabase - With Simple Monitoring."""

import os
import logging
import re
import time
from typing import Optional, Dict

from supabase import create_client, Client
from dotenv import load_dotenv

# Import simple monitoring
from monitoring import monitor_performance, logger, log_context, metrics

load_dotenv()

def get_supabase_client() -> Client:
    """Get a Supabase client instance."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    logger.info("Creating Supabase client", supabase_url=url)
    return create_client(url, key)

def normalize_phone_number(phone_number: str, strip_country_code: bool = False) -> str:
    """Normalize a phone number by removing all non-digit characters."""
    digits_only = re.sub(r'\D', '', phone_number)
    
    if strip_country_code and digits_only.startswith('1') and len(digits_only) > 10:
        return digits_only[1:]
    
    return digits_only

@monitor_performance("business_lookup")
def get_business_by_phone(phone_number: str, call_id: str = None) -> Optional[dict]:
    """Get the business details associated with a phone number."""
    start_time = time.time()
    business_found = False
    
    with log_context(call_id=call_id, operation="business_lookup"):
        try:
            logger.debug("Starting business lookup", phone=phone_number)
            
            supabase = get_supabase_client()
            
            # Try multiple normalizations
            normalized_phone = normalize_phone_number(phone_number)
            normalized_phone_no_country = normalize_phone_number(phone_number, strip_country_code=True)
            
            # Try different phone formats
            formats_to_try = [
                phone_number,
                normalized_phone,
                normalized_phone_no_country,
            ]
            
            if phone_number.startswith('+'):
                formats_to_try.append(phone_number[1:])
                
            # Try each format
            for fmt in formats_to_try:
                logger.debug("Trying phone format", format=fmt)
                response = supabase.table("business_v2").select("id,name,phone").eq("phone", fmt).execute()
                
                if response.data and len(response.data) > 0:
                    business = response.data[0]
                    business_found = True
                    logger.info("Business found", format_used=fmt, business_data=business)
                    return business
            
            # Try ILIKE for special characters
            if any(c in phone_number for c in ['+', '(', ')', ' ', '-']):
                like_phone = phone_number.replace('+', '\\+').replace('(', '\\(').replace(')', '\\)')
                response = supabase.table("business_v2").select("id,name,phone").ilike("phone", like_phone).execute()
                if response.data and len(response.data) > 0:
                    business = response.data[0]
                    business_found = True
                    logger.info("Business found with ILIKE", business_data=business)
                    return business
            
            # Manual comparison as last resort
            all_response = supabase.table("business_v2").select("id,name,phone").execute()
            
            if all_response.data:
                for business in all_response.data:
                    db_phone = business.get("phone", "")
                    
                    if (db_phone == phone_number or
                        normalize_phone_number(db_phone) == normalized_phone or
                        normalize_phone_number(db_phone) == normalized_phone_no_country or
                        (db_phone.startswith('+') and db_phone[1:] == phone_number) or
                        (phone_number.startswith('+') and phone_number[1:] == db_phone)):
                        
                        business_found = True
                        logger.info("Business found with manual comparison", business_data=business)
                        return business
            
            logger.warning("No business found", phone=phone_number)
            return None
                
        except Exception as e:
            logger.error("Business lookup failed", phone=phone_number, error=str(e))
            return None
        finally:
            # Record business lookup metrics
            duration_ms = (time.time() - start_time) * 1000
            status = "success" if business_found else "not_found"
            
            metrics.increment_counter(
                'business_lookup_total',
                labels={'status': status}
            )
            
            logger.info("Business lookup completed",
                       phone=phone_number,
                       business_found=business_found,
                       duration_ms=duration_ms)

def get_business_id_by_phone(phone_number: str, call_id: str = None) -> Optional[str]:
    """Get the business ID associated with a phone number."""
    business = get_business_by_phone(phone_number, call_id=call_id)
    if business:
        return business.get("id")
    return None