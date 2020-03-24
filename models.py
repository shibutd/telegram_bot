import os
from sqlalchemy import create_engine, Column, String, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


engine = create_engine(os.getenv('DATABASE_URL',
                                 'postgresql://user:password@localhost/databasename'))

Base = declarative_base()


class Place(Base):
    __tablename__ = 'places'
    id = Column(Integer, primary_key=True)
    user = Column(Integer)
    address = Column(String(32))
    latitude = Column(Float)
    longitude = Column(Float)
    image = Column(String)

    def __repr__(self):
        return '<Place (%r, %r)>' % self.user, self.address


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()
