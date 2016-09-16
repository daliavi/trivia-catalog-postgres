from flask.ext.seasurf import SeaSurf
from werkzeug.utils import secure_filename
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import service

# for oauth implementation:
from flask import session as login_session
import random, string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests


CLIENT_ID = json.loads(
    open('client_secrets.json','r').read())['web']['client_id']
UPLOAD_FOLDER = './static/avatar'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__)
csrf = SeaSurf(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# registering custom filter for jinja
@app.template_filter('shuffle')
def reverse_filter(s):
    try:
        result = list(s)
        random.shuffle(result)
        return result
    except:
        return s


#  passing user data to base template
@app.context_processor
def inject_user():
    if 'username' not in login_session:
        return dict(user='')
    else:
        user = service.get_user_by_email(login_session['email'])
        if user:
            return dict(user=user.name,
                    picture=user.picture,
                    session_picture=login_session['picture'])
        else:
            return dict(user='',
                        picture='',
                        session_picture='')

######oauth implementation start ###########
# creating anti-forgery state token
@app.route('/login')
def login():
    login_session.clear()
    state = ''.join(
        random.choice(string.ascii_uppercase + string.digits)
        for x in xrange(32)
    )
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/logout')
def logout():
    if 'facebook_id' in login_session:
        return redirect('/fbdisconnect')
    elif 'gplus_id' in login_session:
        return redirect('/gdisconnect')
    else:
        login_session.clear()
        return redirect('/')


@csrf.exempt
@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data

    app_id = json.loads(open('fb_client_secrets.json', 'r').read())['web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
        app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # strip expire tag from access token
    token = result.split("&")[0]

    url = 'https://graph.facebook.com/v2.4/me?%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout,
    # let's strip out the information before the equals sign in our token
    stored_token = token.split("=")[1]
    login_session['access_token'] = stored_token

    # Get user picture
    url = 'https://graph.facebook.com/v2.4/me/picture?%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists in the DB, if not, add.
    user_id = service.get_user_id(login_session['email'])
    if not user_id:
        user_id = service.create_user(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<p3>Connecting as '
    output += login_session['username']
    output += ' </p3>'
    output += '<img class="user-photo" src="'
    output += login_session['picture']
    output += ' "> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (facebook_id,access_token)
    h = httplib2.Http()
    login_session.clear()
    flash("You were logged out")
    return redirect('/')


@csrf.exempt
@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # check if the user is in the database
    user_id = service.get_user_id(email=login_session['email'])
    if not user_id:
        user_id = service.create_user(login_session)

    login_session['user_id'] = user_id

    output = ''
    output += '<p3>Connecting as '
    output += login_session['username']
    output += ' </p3>'
    output += '<img class="user-photo" src="'
    output += login_session['picture']
    output += ' "> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session['access_token']
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        login_session.clear()
        flash("You were logged out")
        return redirect('/')
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response
##### END of Oauth implementation ###############


###### JSON endpoints ##########
# Returns all the categories and questions assigned to them
@app.route('/alldata/JSON')
def testJSON():
    all_data = service.get_all_data()
    return jsonify(all_data)


# return all users
@app.route('/users/JSON')
def usersJSON():
    users = service.get_all_users()
    return jsonify(Users=[i.serialize for i in users])


# return all questions
@app.route('/questions/JSON')
def questionsJSON():
    questions = service.get_all_questions()
    return jsonify(Questions=[i.serialize for i in questions])


# return all categories
@app.route('/categories/JSON')
def categoriesJSON():
    categories = service.get_all_categories()
    return jsonify(Categories=[i.serialize for i in categories])


# return all answers
@app.route('/answers/JSON')
def answersJSON():
    answers = service.get_all_answers()
    return jsonify(Answers=[i.serialize for i in answers])  # Test engpoint to return all questions
##### end of JSON endpoints ######


##### post, get handling ######
@app.route('/question/new/', methods=['GET', 'POST'])
def new_question():
    if ('username' or 'email') not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        answers = [
            (
                request.form['correct_answer'],
                True
            ),
            (
                request.form['alt_answer_1'],
                False
            ),
            (
                request.form['alt_answer_2'],
                False
            ),
            (
                request.form['alt_answer_3'],
                False
            )
        ]

        service.add_question(
            login_session=login_session,
            question=request.form['question'],
            answers=answers,
            categories=request.form.getlist('categories')
        )
        flash('New question created!')
        return redirect('/')
    else:  # if received GET
        categories = service.get_all_categories()
        return render_template('newquestion.html', categories=categories)


@app.route('/category/new/', methods=['GET', 'POST'])
def new_category():
    if ('username' or 'email') not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        service.add_category(
            login_session=login_session,
            category_name=request.form['category_name']
        )
        flash('New category created!')
        return redirect('/')
    else:  # if received GET
        categories = {'biol': '1', 'hist':'2', 'astr':'5'}
        return render_template('newcategory.html', categories=categories)

@app.route('/main')
@app.route('/', methods=['GET'])
def main():
    if request.method == 'GET':
        questions = service.get_all_questions()
        categories = service.get_all_categories()
        return render_template('main.html',
                               categories=categories,
                               questions=questions)


#  how to build URL like /category/<int:category_id>/questions ???
@app.route('/category/<int:category_id>', methods=['GET'])
def questions_by_category(category_id):
    if request.method == 'GET':
        questions = service.get_questions_by_category(
            category_id=category_id
        )
        categories = service.get_all_categories()
        return render_template('main.html',
                               categories=categories,
                               questions=questions)


@app.route('/question/delete/<int:question_id>', methods=['GET', 'POST'])
def delete_question(question_id):
    if ('username' or 'email') not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        if request.form['submit'] == 'Delete':
            error_msg = service.delete_question(
                user_email=login_session['email'],
                question_id=question_id
            )
            if error_msg:
                flash(error_msg)
            else:
                flash('The question was deleted!')
        return redirect('/')

    else:  # if received GET
        question = service.get_question_by_id(
            question_id=question_id
        )
        return render_template('deletequestion.html',
                               question=question)


@app.route('/question/edit/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    if ('username' or 'email') not in login_session:
        print login_session
        return redirect('/login')
    if request.method == 'POST':
        if request.form['submit'] == 'Update':
            question = (
                question_id,
                request.form['question']
            )
            answers = [
                (
                    request.form['correct_answer_id'],
                    request.form['correct_answer']
                ),
                (
                    request.form['alt_answer_1_id'],
                    request.form['alt_answer_1']
                ),
                (
                    request.form['alt_answer_2_id'],
                    request.form['alt_answer_2']
                ),
                (
                    request.form['alt_answer_3_id'],
                    request.form['alt_answer_3']
                )
            ]

            error_msg = service.edit_question(
                user_email=login_session['email'],
                question=question,
                answers=answers,
                categories=request.form.getlist('categories')
            )

            if error_msg:
                flash(error_msg)
            else:
                flash('The question was updated!')
            return redirect('/')
        else:
            return redirect('/')

    else:  # if received GET
        question = service.get_question_by_id(
            question_id=question_id
        )
        categories = service.get_all_categories()
        return render_template('editquestion.html',
                               question=question,
                               categories=categories)


# user for image upload in user_edit()
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/user/edit', methods=['GET', 'POST'])
def user_edit():
    if request.method == 'POST':
        if ('username' or 'email') not in login_session:
            return redirect('/login')

        if request.form['submit'] == 'Upload':
            # check if the post request has the file part
            if 'file' not in request.files:
                flash('No file part')
                return redirect('/user/edit')
            file = request.files['file']
            # if user does not select file, browser also
            # submit a empty part without filename
            if file.filename == '':
                flash('No selected file')
                return redirect('/user/edit')
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                user_id = service.get_user_id(login_session['email'])
                new_filename = str(user_id) + '.' + filename.rsplit('.', 1)[1]
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                file_path = UPLOAD_FOLDER.strip('.') + '/' + new_filename
                service.user_picture_update(
                    user_id=user_id,
                    filepath=file_path)
                flash('The image was successfully uploaded')
                return redirect('/')
        if request.form['submit'] == 'Use':
            user_id = service.get_user_id(login_session['email'])
            service.user_picture_update(
                user_id=user_id,
                filepath=login_session['picture'])
            flash('The image was successfully changed')
            return redirect('/')
        if request.form['submit'] == 'Cancel':
            return redirect('/')

    if request.method == 'GET':
        if ('username' or 'email') not in login_session:
            return redirect('/login')
        user = service.get_user_info(service.get_user_id(login_session['email']))
        return render_template('uploadpicture.html', user=user)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port=5000)