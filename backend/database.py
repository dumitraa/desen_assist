from sqlmodel import create_engine, SQLModel

engine = create_engine("sqlite:///backend/events.db", echo=False)
def init_db():
    SQLModel.metadata.create_all(engine)
    

