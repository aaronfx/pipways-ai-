# ... Database class definition ...

async def init_db():
    """Initialize database connection"""
    await db.connect()

async def close_db():
    """Close database connection"""
    await db.disconnect()
