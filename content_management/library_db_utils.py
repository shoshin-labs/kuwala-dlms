import os
import sqlite3
from sqlite3 import Error

from django.conf import settings


class LibraryDbUtil:

    def __init__(self, metadata_types, metadata, folders, modules, contents, contents_metadata, contents_folder):
        self.metadata_types = metadata_types
        self.metadata = metadata
        self.modules = modules
        self.folders = folders
        self.contents = contents
        self.content_metadata = contents_metadata
        self.content_folder = contents_folder


    def create_connection(self, db_file):
        """ create a database connection to the SQLite database
            specified by db_file
        :param db_file: database file
        :return: Connection object or None
        """
        conn = None
        try:
            conn = sqlite3.connect(db_file)
            return conn
        except Error as e:
            print(e)

        return conn

    def create_table(self, conn, create_table_sql):
        """ create a table from the create_table_sql statement
        :param conn: Connection object
        :param create_table_sql: a CREATE TABLE statement
        :return:
        """
        try:
            c = conn.cursor()
            c.execute(create_table_sql)
        except Error as e:
            raise Exception("error while creating sql tables:" + str(e))

    def insert_data(self, conn):
        """ insert bulk data from DLMS to sqlite
        :param conn: Connection object
        :return:
        """
        try:
            c = conn.cursor()
            c.executemany('INSERT INTO metadata_type VALUES (?,?)', self.metadata_types)
            c.executemany('INSERT INTO metadata VALUES (?,?,?,?)', self.metadata)
            c.executemany('INSERT INTO folder VALUES (?,?,?,?)', self.folders)
            c.executemany('INSERT INTO module VALUES (?,?,?)', self.modules)
            c.executemany('INSERT INTO content VALUES (?,?,?,?,?,?,?,?,?)', self.contents)
            c.executemany('INSERT INTO content_metadata VALUES (?,?)', self.content_metadata)
            c.executemany('INSERT INTO content_folder VALUES (?,?,?,?,?)', self.content_folder)
        except Error as e:
            raise Exception("error while inserting data into tables:" + str(e))

    def create_library_db(self, build_path):
        database = os.path.join(build_path, 'solarspell.db')
        sql_create_metadata_type_table = """CREATE TABLE IF NOT EXISTS metadata_type (
                                        id INTEGER PRIMARY KEY,
                                        type_name TEXT NOT NULL
                                    );"""
        sql_create_metadata_table = """CREATE TABLE IF NOT EXISTS metadata (
                                        id INTEGER PRIMARY KEY,
                                        meta_name TEXT NOT NULL,
                                        type_name TEXT NOT NULL,
                                        type_id INTEGER NOT NULL, 
                                        FOREIGN KEY (type_id) REFERENCES metadata_type (id)
                                    );"""
        sql_create_folder_table = """ CREATE TABLE IF NOT EXISTS folder (
                                            id INTEGER PRIMARY KEY,
                                            folder_name TEXT NOT NULL,
                                            logo TEXT,
                                            parent_id INTEGER, 
                                            FOREIGN KEY (parent_id) REFERENCES folder (id)
                                        );"""
        sql_create_module_table = """ CREATE TABLE IF NOT EXISTS module (
                                            id INTEGER PRIMARY KEY,
                                            module_name TEXT NOT NULL,
                                            logo TEXT
        );                                 """
        sql_create_content_table = """ CREATE TABLE IF NOT EXISTS content (
                                            id INTEGER PRIMARY KEY,
                                            title text NOT NULL,
                                            description TEXT,
                                            file_name TEXT,
                                            published_date TEXT,
                                            copyright_notes TEXT,
                                            rights_statement TEXT,
                                            file_size REAL,
                                            keywords TEXT
                                        ); """
        sql_create_content_metadata_table = """ CREATE TABLE IF NOT EXISTS content_metadata (
                                               content_id INTEGER NOT NULL,
                                               metadata_id INTEGER NOT NULL,
                                               FOREIGN KEY (content_id) REFERENCES content (id)                                                               
                                               FOREIGN KEY (metadata_id) REFERENCES metadata (id)                             
                                           ); """
        sql_create_content_folder_table = """ CREATE TABLE IF NOT EXISTS content_folder (
                                               id INTEGER NOT NULL,
                                               folder_id INTEGER NOT NULL,
                                               title TEXT,
                                               file_name TEXT,
                                               file_size REAL,
                                               FOREIGN KEY (id) REFERENCES content (id)                                                               
                                               FOREIGN KEY (folder_id) REFERENCES folder (id)                             
                                           ); """
        sql_create_content_fts_table = """ CREATE VIRTUAL TABLE content_fts USING fts5(
                                                title,
                                                file_name UNINDEXED,
                                                description,
                                                file_size UNINDEXED,
                                                keywords,
                                                content = 'content',
                                                content_rowid = 'id'                            
                                           ); """
        sql_create_content_fts_trigger = """CREATE TRIGGER content_ai AFTER INSERT ON content
                                            BEGIN
                                                INSERT INTO content_fts (rowid, title, file_name, description, file_size, keywords)
                                                VALUES (new.id, new.title, new.file_name, new.description, new.file_size, new.keywords);
                                            END;"""

        # create a database connection
        conn = self.create_connection(database)

        if conn is not None:
            # create tables
            self.create_table(conn, sql_create_metadata_type_table)
            self.create_table(conn, sql_create_metadata_table)
            self.create_table(conn, sql_create_folder_table)
            self.create_table(conn, sql_create_module_table)
            self.create_table(conn, sql_create_content_table)
            self.create_table(conn, sql_create_content_metadata_table)
            self.create_table(conn, sql_create_content_folder_table)
            self.create_table(conn, sql_create_content_fts_table)
            self.create_table(conn, sql_create_content_fts_trigger)
            # insert data
            self.insert_data(conn)
            conn.commit()
        else:
            raise Exception("Error! cannot create the database connection.")
        conn.close()
