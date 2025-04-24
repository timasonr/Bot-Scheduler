# Telegram Task Planner Bot

A simple task scheduler bot for Telegram built with Python and aiogram 3.x.

## Features

- Create tasks with names and deadlines
- View all your tasks in a list
- Mark tasks as completed
- Edit task names and deadlines
- Delete tasks
- Task reminders at 24 hours, 1 hour, and 5 minutes before deadline
- Notification when a task is due
- User-friendly button interface with calendar selector

## Installation

1. Install the required dependencies:
```
pip install -r requirements.txt
```

2. Open the `bot.py` file and replace the token line with your own token:
```python
BOT_TOKEN = "your_bot_token_here"  # Replace with your actual token
```

To get a bot token, talk to [BotFather](https://t.me/BotFather) on Telegram.

## Running the Bot

```
python bot.py
```

## Bot Commands

- `/start` - Start the bot
- `/tasks` - View all tasks
- `/add` - Add a new task
- `/help` - Get help information

The bot also provides buttons for easy navigation and task management.

## Project Structure

- `bot.py` - Main bot code with all handlers and functionality
- `requirements.txt` - Required Python packages
- `README.md` - Project documentation

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
