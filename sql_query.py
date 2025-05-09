"""Execute raw SQL query against Supabase."""

import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def run_sql_query():
    """Execute a SQL query directly against the Supabase database."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        return
    
    logger.info(f"Using Supabase URL: {url}")
    logger.info(f"Using Supabase Key: {key[:5]}...{key[-5:] if len(key) > 10 else ''}")
    
    try:
        # Initialize Supabase client
        supabase = create_client(url, key)
        
        # SQL query to find businesses with phone numbers
        sql = """
        SELECT id, name, phone
        FROM business_v2
        """
        
        # Execute the query
        response = supabase.rpc('select_business_by_phone').execute()
        
        if response.data:
            logger.info(f"Found {len(response.data)} businesses via RPC:")
            for business in response.data:
                logger.info(f"ID: {business.get('id')} | Name: {business.get('name')} | Phone: {business.get('phone')}")
        else:
            logger.warning("No businesses found or RPC function not available")
            
            # Try regular table query
            response = supabase.table("business_v2").select("*").execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} businesses via table query:")
                for business in response.data:
                    logger.info(f"ID: {business.get('id')} | Name: {business.get('name')} | Phone: {business.get('phone')}")
            else:
                logger.error("No businesses found via regular query either")
        
    except Exception as e:
        logger.error(f"Error executing SQL query: {str(e)}")

if __name__ == "__main__":
    run_sql_query()