from sqlmodel import create_engine, SQLModel

# sqlite
engine = create_engine("sqlite:///./events.db", echo=False)
# engine = create_engine(
#     "postgresql+psycopg2://digitizer_api:test@localhost/digitizer_db",
#     pool_size=20, max_overflow=40, pool_pre_ping=True
# )

def init_db():
    SQLModel.metadata.create_all(engine)
    

