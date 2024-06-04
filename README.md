# SolarSPELL-DLMS

This is the latest repository for the DLMS, which is one tool used to create the software loaded on a SolarSPELL. More information about SolarSPELL can be found [here](http://solarspell.org/).

## Installation

Before installation of the DLMS, make sure that Python 3.8+ and Node >= 10, <= 16 are installed.

Create a python venv 

### Env File

Duplicate `env.example` from the /dlms directory, change the appropriate values, and rename it `.env`. This step must be done before the following steps will work.

### Python virutal envirorment 
```bash
python -m venv <EnvirormentName>
```

Activate to enter in envirorment
Navigate to venv\Scripts
```bash
python acitvate
```
Should look like this when activated 
(venv) D:\SollarSpell\solarspell-dlms\venv\Scripts>

### Python Dependencies




To install python dependencies, run this command in the base directory.
#### psycopg2
Install psycopg2
```bash
pip install psycopg2-binary
```

#### Pillow
For errors encountered installing Pillow: link[https://pillow.readthedocs.io/en/latest/installation.html]
It seems like the version of Pillow listed in the requirements.txt is too old for the latest releases of python, so it will need to be updated.
Pillow might also be completely unused? This needs to be tested though.

djangorestframework needs to be updated?
Install pillow 
```bash
python -m pip install Pillow 
```

#### After pillow and psycopg2
```bash
pip install -r requirements.txt
```
Inside env file specify 
DATABASE_URL=postgres://username:password@hostname:port/database

### Database

Create a PostgreSQL user and database.
```
sudo -u postgres createuser --interactive
sudo -u postgres createdb dlms
sudo -u postgres psql
ALTER USER username WITH PASSWORD 'password'
```

### DB Migration

To initialize the database with the proper schema, you must run the following command in the base directory.

```bash
python manage.py migrate
```

### Load in data 

In psql tool 

Include single quotes 

\i 'path to sql file' 

### Starting the Server

To start the server, you must run the following command in the base directory.

```bash
python manage.py runserver
```

navigate to localhost:8000/static/index.html

### Frontend

To setup the NPM environment, you must run npm install in the frontend directory and then add the node_modules bin to your path.

```
cd frontend
npm install
add the node_modules/.bin/ to PATH Environment Variable - Required.
```

### Build Frontend

There are three build scripts depending on your environment. You may have to try them all to see which one works for you.

**Mac**

```
npm run-script build
```

**Bash/Linux**

```
npm run-script build-bash
```

**Windows**

```
npm run-script winbuild
```
### 
After building front end 
