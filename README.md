# Trivia Database with PostgreSQL
Trivia database is used to manage trivia categories, questions and answers. Users can login with their Facebook or Google accounts.
The project create using Flask Python, SQLAlchemy with PostgreSQL database, Facebook and Google OAuth. 

# Features
- Login/logout with Facebook or Google
- Update profile picture
- Create a category
- Create/update/delete a question and possible answers
- Create/update/delete can be performed only by logged in users.
- Update and delete can be done only by the same user who created the record.
- Filter questions by a category
- Get all the categories and questions belonging to them in JSON format /alldata/JSON
- CSRF on forms


##Prerequisites
- Python (tested with version 2.7.6)
- PostgreSQL 9.3
- Virtual Box and Vagrant
- Sqlalchemy version 1.0 or higher (tested with 1.0.14)
- flask-seasurf (for CSRF protection)

##Steps
To run the project on a virtual machine:
- download Vagrant configuration from https://github.com/udacity/fullstack-nanodegree-vm
- download project files to /vagrant/catalog directory
- Upgrade SQLAlchemy if needed:
- `$sudo pip install SQLAlchemy --upgrade`
- Import Flask SeaSurf library
- `$sudo pip install flask-seasurf`
- in vagrant.catalog directory create 2 files client_secrets.json with Goggle secret and fb_client_secrets.json with Facebook app secret.
- to start the project in vagrant/catalog directory run `$python project.py`
- access the project on localhost:5000