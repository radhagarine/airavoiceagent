"""Knowledge base interface for retrieving information from the vector database."""

import os
import logging
from typing import List, Optional
from pathlib import Path

import lancedb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class KnowledgeBase:
    """Interface to query the LanceDB knowledge base."""
    
    def __init__(self, db_path: str = None):
        """Initialize the knowledge base with the LanceDB connection.
        
        Args:
            db_path: Path to the LanceDB database. If None, uses environment variable.
        """
        # Use the provided path, or get from environment, or use default
        if db_path is None:
            db_path = os.getenv("LANCEDB_PATH")
            
        if not db_path:
            raise ValueError(
                "LanceDB path not provided. Please set LANCEDB_PATH environment variable "
                "or provide db_path parameter pointing to your LanceDB data directory."
            )
            
        logger.info(f"Using LanceDB path: {db_path}")
        
        # Verify the path exists
        if not os.path.exists(db_path):
            logger.warning(f"LanceDB path {db_path} does not exist.")
            # We'll let LanceDB handle this - it might create the directory or raise an error
        
        self.db_path = db_path
        self.db = lancedb.connect(db_path)
        
        # Initialize the embedding model for encoding queries
        # Using the same model that was used to create the vectors
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info(f"Initialized KnowledgeBase with LanceDB at {db_path}")
    
    def get_business_table_name(self, business_id: str) -> str:
        """Generate the table name for a business.
        
        Args:
            business_id: The ID of the business
            
        Returns:
            The table name for the business's knowledge base
        """
        return f"business_{business_id}"
    
    def business_has_knowledge_base(self, business_id: str) -> bool:
        """Check if a business has a knowledge base table.
        
        Args:
            business_id: The ID of the business
            
        Returns:
            True if the business has a knowledge base, False otherwise
        """
        table_name = self.get_business_table_name(business_id)
        return table_name in self.db.table_names()
    
    def query(self, business_id: str, query_text: str, top_k: int = 3) -> List[str]:
        """Query the knowledge base for a business.
        
        Args:
            business_id: The ID of the business
            query_text: The query text to search for
            top_k: The number of top results to return
            
        Returns:
            A list of relevant text chunks from the knowledge base
        """
        table_name = self.get_business_table_name(business_id)
        
        # Check if the table exists
        if not self.business_has_knowledge_base(business_id):
            logger.warning(f"No knowledge base found for business {business_id}")
            return []
        
        try:
            # Open the table
            table = self.db.open_table(table_name)
            
            # Encode the query text
            query_vector = self.model.encode(query_text)
            
            # Search the table
            results = table.search(query_vector).limit(top_k).to_list()
            
            # Extract the text chunks
            text_chunks = [result.get("text", "") for result in results if "text" in result]
            
            logger.info(f"Found {len(text_chunks)} relevant chunks for query: {query_text[:50]}...")
            return text_chunks
            
        except Exception as e:
            logger.error(f"Error querying knowledge base: {str(e)}")
            return []