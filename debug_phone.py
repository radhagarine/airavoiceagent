"""Debug script to test the phone number lookup directly."""

import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import the helper function
from utils.supabase_helper import get_business_by_phone, normalize_phone_number
from supabase import create_client, Client

# Test phone number
TEST_NUMBERS = [
    "+18554494055",
    "18554494055",
    "8554494055",
    "(855) 449-4055",
    "+1(855) 449-4055"
]

def get_all_businesses():
    """Get all businesses from the database for debugging."""
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
            return []
        
        supabase = create_client(url, key)
        response = supabase.table("business_v2").select("id,name,phone").execute()
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        logger.error(f"Error getting all businesses: {str(e)}")
        return []

def main():
    """Test the phone number lookup with different formats."""
    logger.info("Starting phone number lookup test")
    
    # First, get all businesses for reference
    businesses = get_all_businesses()
    logger.info(f"Found {len(businesses)} businesses in the database:")
    for b in businesses:
        logger.info(f"ID: {b.get('id')} | Name: {b.get('name')} | Phone: {b.get('phone')}")
    
    for phone in TEST_NUMBERS:
        logger.info(f"\n\nTesting phone number: {phone}")
        
        # Show normalized versions
        logger.info(f"Normalized with country code: {normalize_phone_number(phone)}")
        logger.info(f"Normalized without country code: {normalize_phone_number(phone, strip_country_code=True)}")
        
        # Try to look up the business
        business = get_business_by_phone(phone)
        
        if business:
            logger.info(f"SUCCESS: Found business for {phone}:")
            logger.info(f"ID: {business.get('id')}")
            logger.info(f"Name: {business.get('name')}")
            logger.info(f"Phone in DB: {business.get('phone')}")
        else:
            logger.error(f"FAILED: No business found for {phone}")

if __name__ == "__main__":
    main()