# WordBox – vocabulary website + Telegram bot (Django)

    pip install -r requirements.txt
    python manage.py migrate
    python manage.py createsuperuser   # optional (admin)
    python manage.py runserver

Telegram: create a bot with @BotFather, then

    export TELEGRAM_BOT_TOKEN=123:ABC
    python manage.py runbot            # keep running (long polling)

Daily reminders (cron, e.g. every day 09:00):

    0 9 * * * cd /path/to/vocab && TELEGRAM_BOT_TOKEN=... python manage.py send_reminders

Set TIME_ZONE (e.g. `export TIME_ZONE=Europe/London`) so "due today" matches your day.
Link accounts: sign up on the site, open the dashboard, send `/link CODE` to the bot.
