import asyncio
from sqlalchemy import text
from app.database import engine

async def main():
    async with engine.connect() as conn:
        query = """
        SELECT 
            m.created_at AS timestamp,
            c.id AS conversation_id,
            c.title AS conversation_title,
            c.knowledge_mode,
            m.content AS user_question
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE m.role = 'user'
        ORDER BY m.created_at DESC;
        """
        result = await conn.execute(text(query))
        rows = result.fetchall()
        
        print(f"Found {len(rows)} user questions:\n")
        print("| Timestamp | Conversation ID | Title | Mode | User Question |")
        print("| --- | --- | --- | --- | --- |")
        for row in rows:
            # strip newlines from question for table formatting
            q_clean = str(row.user_question).replace('\n', ' ').strip()
            print(f"| {row.timestamp} | {row.conversation_id} | {row.conversation_title} | {row.knowledge_mode} | {q_clean} |")

if __name__ == "__main__":
    asyncio.run(main())
