rm -r system/migrations
rm -r accounts/migrations


rm db.sqlite3

pip install -r requirements.txt

python manage.py makemigrations system accounts
python manage.py migrate
python manage.py loaddata system/initial_fixtures/initial_fixtures.json
#python manage.py loaddata accounts/initial_fixtures/initial_fixtures.json