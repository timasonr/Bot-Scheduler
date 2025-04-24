import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Logging setup
logging.basicConfig(level=logging.INFO)

# Bot token (directly in the code)
BOT_TOKEN = "enter your token here"  # Replace with your real token

# Creating bot and dispatcher objects
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Dictionary for storing user tasks: {user_id: {task_id: {name, deadline, completed, reminded}}}
tasks = {}

# Dictionary for tracking reminders
reminders = {}

# States for the state machine
class TaskStates(StatesGroup):
    waiting_for_task_name = State()
    waiting_for_date_selection = State()
    waiting_for_time_selection = State()
    waiting_for_edit_name = State()
    waiting_for_edit_deadline = State()

# Helper functions
def get_task_keyboard(user_id, task_id=None):
    kb = InlineKeyboardBuilder()
    
    if task_id is not None:
        # Buttons for a specific task
        kb.button(text="✅ Completed", callback_data=f"complete_{task_id}")
        kb.button(text="✏️ Edit", callback_data=f"edit_{task_id}")
        kb.button(text="🗑️ Delete", callback_data=f"delete_{task_id}")
        kb.button(text="« Back", callback_data="list_tasks")
        kb.adjust(2, 2)
    else:
        # Show user's task list
        if user_id in tasks and tasks[user_id]:
            for task_id, task in tasks[user_id].items():
                status = "✅" if task["completed"] else "⏳"
                kb.button(
                    text=f"{status} {task['name']} ({task['deadline']})",
                    callback_data=f"view_{task_id}"
                )
            kb.adjust(1)
        kb.button(text="➕ Add Task", callback_data="add_task")
        kb.adjust(1)
    
    return kb.as_markup()

def get_main_keyboard():
    # Create a keyboard with main commands
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 My Tasks"), KeyboardButton(text="➕ Add Task")],
            [KeyboardButton(text="ℹ️ Help")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def send_reminder(user_id, task_id, time_until_deadline):
    """Sends a reminder about the task"""
    if user_id in tasks and task_id in tasks[user_id]:
        task = tasks[user_id][task_id]
        
        # Check that the task is not marked as completed
        if not task["completed"]:
            # Determine the message depending on the time until deadline
            if time_until_deadline.days == 1:  # 24 hours before
                message = (
                    f"⏰ <b>Reminder!</b>\n\n"
                    f"Task <b>{task['name']}</b> is due in 24 hours\n"
                    f"Deadline: {task['deadline']}"
                )
            elif time_until_deadline.seconds <= 3600 and time_until_deadline.seconds > 300:  # 1 hour before
                message = (
                    f"⏰ <b>Reminder!</b>\n\n"
                    f"Task <b>{task['name']}</b> is due in 1 hour\n"
                    f"Deadline: {task['deadline']}"
                )
            elif time_until_deadline.seconds <= 300 and time_until_deadline.seconds > 0:  # 5 minutes before
                message = (
                    f"⚠️ <b>Urgent Reminder!</b>\n\n"
                    f"Task <b>{task['name']}</b> is due in 5 minutes\n"
                    f"Deadline: {task['deadline']}"
                )
            elif time_until_deadline.total_seconds() <= 0:  # At deadline moment
                message = (
                    f"🔔 <b>Time's up!</b>\n\n"
                    f"Task <b>{task['name']}</b> is due now\n"
                    f"Deadline: {task['deadline']}"
                )
            else:
                return  # Don't send reminders for other intervals
            
            # Send reminder
            await bot.send_message(
                user_id,
                message,
                parse_mode="HTML",
                reply_markup=get_task_keyboard(user_id, task_id)
            )
            
            # Update reminder flag for this interval
            if not "reminded_at" in task:
                task["reminded_at"] = []
                
            # Add current time to the list of sent reminders
            task["reminded_at"].append(datetime.now().strftime("%d.%m.%Y %H:%M"))

async def check_deadlines():
    """Periodically checks deadlines and sends reminders"""
    while True:
        now = datetime.now()
        
        for user_id in tasks:
            for task_id, task in list(tasks[user_id].items()):
                # Skip completed tasks
                if task.get("completed"):
                    continue
                
                try:
                    # Determine date format
                    if len(task["deadline"].split()) == 1:
                        # Only date (add 23:59)
                        deadline = datetime.strptime(f"{task['deadline']} 23:59", "%d.%m.%Y %H:%M")
                    else:
                        # Date and time
                        deadline = datetime.strptime(task["deadline"], "%d.%m.%Y %H:%M")
                    
                    # Calculate time until deadline
                    time_diff = deadline - now
                    
                    # List of reminders that have already been sent
                    reminded_at = task.get("reminded_at", [])
                    
                    # Check different intervals for reminders
                    
                    # 24 hours before (check that the reminder has not been sent yet)
                    if time_diff.days == 1 and now.strftime("%d.%m.%Y") not in "".join(reminded_at):
                        await send_reminder(user_id, task_id, time_diff)
                    
                    # 1 hour before (check that the reminder has not been sent in the current hour)
                    elif time_diff.seconds <= 3600 and time_diff.seconds > 3540 and now.strftime("%d.%m.%Y %H") not in "".join(reminded_at):
                        await send_reminder(user_id, task_id, time_diff)
                    
                    # 5 minutes before (check that the reminder has not been sent in the current 5 minutes)
                    elif time_diff.seconds <= 300 and time_diff.seconds > 240 and now.strftime("%d.%m.%Y %H:%M") not in "".join(reminded_at):
                        await send_reminder(user_id, task_id, time_diff)
                    
                    # At deadline moment (± 1 minute)
                    elif abs(time_diff.total_seconds()) < 60 and now.strftime("%d.%m.%Y %H:%M") not in "".join(reminded_at):
                        await send_reminder(user_id, task_id, time_diff)
                    
                except ValueError:
                    # Date format error - skip
                    continue
        
        # Check every 30 seconds
        await asyncio.sleep(30)

# /start command handler
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Hello! I'm a scheduler bot that will help you manage your tasks.\n\n"
        "Use the buttons below to manage tasks or the following commands:\n"
        "/tasks - view all tasks\n"
        "/add - add a new task\n"
        "/help - get help",
        reply_markup=get_main_keyboard()
    )

# /help command and help button handler
@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Help")
async def cmd_help(message: Message):
    await message.answer(
        "🔍 <b>Command Help</b>\n\n"
        "📋 My Tasks - view all tasks\n"
        "➕ Add Task - create a new task\n"
        "ℹ️ Help - show this help\n\n"
        "The bot will remind you 1 hour before the task is due.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# /tasks command and "My Tasks" button handler
@dp.message(Command("tasks"))
@dp.message(F.text == "📋 My Tasks")
async def cmd_tasks(message: Message):
    user_id = message.from_user.id
    
    if user_id not in tasks or not tasks[user_id]:
        await message.answer(
            "You don't have any tasks yet. Add a new task using the button below.",
            reply_markup=get_task_keyboard(user_id)
        )
    else:
        await message.answer(
            "📋 <b>Your tasks:</b>",
            reply_markup=get_task_keyboard(user_id),
            parse_mode="HTML"
        )

# /add command and "Add Task" button handler
@dp.message(Command("add"))
@dp.message(F.text == "➕ Add Task")
async def cmd_add(message: Message, state: FSMContext):
    await message.answer("Enter the task name:")
    await state.set_state(TaskStates.waiting_for_task_name)

# Task name handler
@dp.message(TaskStates.waiting_for_task_name)
async def process_task_name(message: Message, state: FSMContext):
    await state.update_data(task_name=message.text.strip())
    
    await message.answer(
        "Let's choose a deadline for the task. "
        "Select a date from the calendar:",
        reply_markup=get_month_keyboard()
    )
    
    await state.set_state(TaskStates.waiting_for_date_selection)

# Functions for creating date and time keyboards
def get_month_keyboard():
    """Creates a keyboard for month selection"""
    kb = InlineKeyboardBuilder()
    
    months = [
        "January", "February", "March", "April", 
        "May", "June", "July", "August",
        "September", "October", "November", "December"
    ]
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    # Add header
    kb.button(text="Select Month", callback_data="ignore")
    
    # Form month groups by seasons for the current year
    seasons = []
    # Winter of current year (including December of previous year)
    if current_month <= 2:
        seasons.append([(12, current_year-1, "December"), (1, current_year, "January"), (2, current_year, "February")])
    # Spring
    if current_month <= 5:
        seasons.append([(3, current_year, "March"), (4, current_year, "April"), (5, current_year, "May")])
    # Summer
    if current_month <= 8:
        seasons.append([(6, current_year, "June"), (7, current_year, "July"), (8, current_year, "August")])
    # Autumn
    if current_month <= 11:
        seasons.append([(9, current_year, "September"), (10, current_year, "October"), (11, current_year, "November")])
    # Winter of next year
    seasons.append([(12, current_year, "December"), (1, current_year+1, "January"), (2, current_year+1, "February")])
    
    # If current month is after February, also add spring of next year
    if current_month > 2:
        seasons.append([(3, current_year+1, "March"), (4, current_year+1, "April"), (5, current_year+1, "May")])
    
    # Add seasonal month groups
    for season in seasons:
        for month_num, year, month_name in season:
            # Check that the month is not in the past
            if year > current_year or (year == current_year and month_num >= current_month):
                # Highlight the current month
                if month_num == current_month and year == current_year:
                    kb.button(
                        text=f"• {month_name} {year}",
                        callback_data=f"month_{month_num}_{year}"
                    )
                else:
                    kb.button(
                        text=f"{month_name} {year}",
                        callback_data=f"month_{month_num}_{year}"
                    )
    
    # Add cancel button
    kb.button(text="Cancel", callback_data="hide_calendar")
    
    # Determine optimal layout
    # Number of available months
    num_months = sum(sum(1 for m, y, _ in season if y > current_year or (y == current_year and m >= current_month)) for season in seasons)
    
    # Basic layout: 1 header button, 1 cancel button
    layout = [1]
    
    # Add rows with 3 months each
    buttons_per_row = 3
    
    # Full rows
    full_rows = num_months // buttons_per_row
    for _ in range(full_rows):
        layout.append(buttons_per_row)
    
    # Remaining buttons
    remaining = num_months % buttons_per_row
    if remaining > 0:
        layout.append(remaining)
    
    # Cancel button
    layout.append(1)
    
    # Apply layout
    kb.adjust(*layout)
    
    return kb.as_markup()

def get_day_keyboard(month, year):
    """Creates a keyboard for day selection"""
    kb = InlineKeyboardBuilder()
    
    # Determine the number of days in the month
    if month in [4, 6, 9, 11]:
        days_in_month = 30
    elif month == 2:
        # Check for leap year
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            days_in_month = 29
        else:
            days_in_month = 28
    else:
        days_in_month = 31
    
    # Current date
    current_date = datetime.now().date()
    
    # For the current month, show only days starting from today
    start_day = 1
    if month == current_date.month and year == current_date.year:
        start_day = current_date.day
    
    # Get the first day of the month and the starting display day
    first_day = datetime(year, month, 1)
    start_display_day = datetime(year, month, start_day)
    
    # Determine which day of the week the display starts (0 - Monday, 6 - Sunday)
    start_weekday = start_display_day.weekday()
    
    # Collect available days
    available_days = []
    for day in range(start_day, days_in_month + 1):
        # Format current day differently
        if day == current_date.day and month == current_date.month and year == current_date.year:
            available_days.append((day, f"[{day}]"))
        else:
            available_days.append((day, f"{day}"))
    
    # If there are no available days, just show a message and navigation buttons
    if not available_days:
        kb.button(text="There are no available days in this month", callback_data="ignore")
        kb.button(text="« Back", callback_data="back_to_month")
        kb.button(text="Cancel", callback_data="hide_calendar")
        kb.adjust(1, 2)
        return kb.as_markup()
    
    # Calculate optimal number of buttons per row for available days
    # Standard is 7 (for days of the week)
    buttons_per_row = 7
    
    # Add available days to calendar
    for day, text in available_days:
        kb.button(
            text=text,
            callback_data=f"day_{day}_{month}_{year}"
        )
    
    # Add navigation buttons
    kb.button(text="« Back", callback_data="back_to_month")
    kb.button(text="Cancel", callback_data="hide_calendar")
    kb.button(text="Today", callback_data=f"day_{current_date.day}_{current_date.month}_{current_date.year}")
    
    # Configure button layout
    
    # Then place available days
    # Calculate number of rows needed for available days
    num_day_rows = (len(available_days) + buttons_per_row - 1) // buttons_per_row
    
    layout = []
    # Add full rows
    for _ in range(num_day_rows - 1):
        layout.append(buttons_per_row)
    
    # Add last row with remaining buttons
    remaining_buttons = len(available_days) % buttons_per_row
    if remaining_buttons > 0:
        layout.append(remaining_buttons)
    else:
        layout.append(buttons_per_row)
    
    # Add row for navigation buttons
    layout.append(3)
    
    # Apply layout
    kb.adjust(*layout)
    
    return kb.as_markup()

# Date and time selection handlers
@dp.callback_query(F.data.startswith("month_"))
async def process_month_selection(callback: CallbackQuery, state: FSMContext):
    """Handles month selection"""
    await callback.answer()
    
    # Get month and year from callback_data
    _, month, year = callback.data.split("_")
    month, year = int(month), int(year)
    
    # Save selected month and year
    await state.update_data(selected_month=month, selected_year=year)
    
    # Determine month name
    months = [
        "January", "February", "March", "April", 
        "May", "June", "July", "August",
        "September", "October", "November", "December"
    ]
    month_name = months[month - 1]
    
    # Show calendar with days
    await callback.message.edit_text(
        f"{month_name}, {year}\nSelect Day:",
        reply_markup=get_day_keyboard(month, year)
    )

@dp.callback_query(F.data == "back_to_month")
async def process_back_to_month(callback: CallbackQuery):
    """Return to month selection"""
    await callback.answer()
    await callback.message.edit_text(
        "Select Month:",
        reply_markup=get_month_keyboard()
    )

@dp.callback_query(F.data.startswith("day_"))
async def process_day_selection(callback: CallbackQuery, state: FSMContext):
    """Handles day selection"""
    await callback.answer()
    
    # Get day, month and year from callback_data
    _, day, month, year = callback.data.split("_")
    day, month, year = int(day), int(month), int(year)
    
    # Save selected day
    await state.update_data(selected_day=day)
    
    # Form date for display
    date_str = f"{day:02d}.{month:02d}.{year}"
    
    # Get month name
    months = [
        "January", "February", "March", "April", 
        "May", "June", "July", "August",
        "September", "October", "November", "December"
    ]
    month_name = months[month - 1]
    
    # Save date as string
    await state.update_data(date_str=date_str)
    
    # Check if the selected date is the current day
    now = datetime.now()
    is_today = (day == now.day and month == now.month and year == now.year)
    
    # Create keyboard with hours, taking into account the current day
    kb = InlineKeyboardBuilder()
    
    # Add time header
    kb.button(text="⏰ Select Time", callback_data="ignore")
    
    # Determine available hours
    available_hours = []
    if is_today:
        # For the current day, display only future hours
        current_hour = now.hour
        available_hours = list(range(current_hour, 24))
    else:
        # For other days, display all hours
        available_hours = list(range(0, 24))
    
    # Add available hours
    for hour in available_hours:
        kb.button(text=f"{hour}:00", callback_data=f"hour_{hour:02d}")
    
    # Add "All day" option
    kb.button(text="📆 All Day (no time)", callback_data="time_all_day")
    
    # Add navigation buttons
    kb.button(text="« Back to Day Selection", callback_data="back_to_day")
    kb.button(text="Cancel", callback_data="hide_calendar")
    
    # Configure button layout depending on the number of available hours
    if len(available_hours) > 0:
        # Calculate optimal number of buttons per row
        buttons_per_row = min(6, len(available_hours))
        
        # Create rows with buttons_per_row buttons each
        rows = [buttons_per_row] * (len(available_hours) // buttons_per_row)
        
        # Add remaining buttons to the last row
        if len(available_hours) % buttons_per_row > 0:
            rows.append(len(available_hours) % buttons_per_row)
        
        # Add rows for header and navigation buttons
        kb.adjust(1, *rows, 1, 2)
    else:
        # If there are no available hours, just display "All day" option and navigation
        kb.adjust(1, 1, 2)
    
    # Show time selection with better date formatting
    await callback.message.edit_text(
        f"📅 <b>Selected Date:</b> {day} {month_name} {year}\n\n"
        f"⏰ Select Time:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_day")
async def process_back_to_day(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору дня"""
    await callback.answer()
    
    # Получаем сохраненные месяц и год
    user_data = await state.get_data()
    month = user_data.get("selected_month")
    year = user_data.get("selected_year")
    
    if month and year:
        await callback.message.edit_text(
            "Выберите день:",
            reply_markup=get_day_keyboard(month, year)
        )
    else:
        # Если данные потеряны, возвращаемся к выбору месяца
        await callback.message.edit_text(
            "Выберите месяц:",
            reply_markup=get_month_keyboard()
        )

@dp.callback_query(F.data.startswith("hour_"))
async def process_hour_selection(callback: CallbackQuery, state: FSMContext):
    """Handles hour selection"""
    await callback.answer()
    
    hour = callback.data.split("_")[1]
    await state.update_data(selected_hour=hour)
    
    # Get user data
    user_data = await state.get_data()
    selected_day = int(user_data.get("selected_day"))
    selected_month = int(user_data.get("selected_month"))
    selected_year = int(user_data.get("selected_year"))
    
    # Get current time
    now = datetime.now()
    
    # Check if current day and hour are selected
    is_today = (selected_day == now.day and 
               selected_month == now.month and 
               selected_year == now.year)
    selected_hour = int(hour)
    is_current_hour = is_today and selected_hour == now.hour
    
    # Create keyboard for minute selection
    kb = InlineKeyboardBuilder()
    
    # Header
    kb.button(text=f"⏰ Selected: {hour}:__", callback_data="ignore")
    
    # Determine available minutes
    available_minutes = []
    if is_current_hour:
        # For current hour, display only future minutes, rounded to 5
        current_minute = now.minute
        rounded_current_minute = (current_minute // 5 + 1) * 5  # Round up to nearest 5 minutes
        if rounded_current_minute < 60:
            available_minutes = list(range(rounded_current_minute, 60, 5))
        # If no available minutes in current hour,
        # function will return empty list and we'll display appropriate message
    else:
        # For other hours, display all minutes
        available_minutes = list(range(0, 60, 5))
    
    # Add available minutes
    for m in available_minutes:
        kb.button(text=f"{hour}:{m:02d}", callback_data=f"fulltime_{hour}:{m:02d}")
    
    # Navigation buttons
    kb.button(text="« Back to Time Selection", callback_data="back_to_time")
    kb.button(text="Cancel", callback_data="hide_calendar")
    
    # Configure button layout depending on number of available minutes
    if len(available_minutes) > 0:
        # Calculate optimal number of buttons per row
        buttons_per_row = min(4, len(available_minutes))
        
        # Create rows with buttons_per_row buttons each
        rows = [buttons_per_row] * (len(available_minutes) // buttons_per_row)
        
        # Add remaining buttons to last row
        if len(available_minutes) % buttons_per_row > 0:
            rows.append(len(available_minutes) % buttons_per_row)
        
        # Add rows for header and navigation buttons
        kb.adjust(1, *rows, 2)
    else:
        message_text = (
            f"No available minutes for {hour}:00.\n"
            f"Please select another hour."
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="« Back to Time Selection", callback_data="back_to_time")
        await callback.message.edit_text(message_text, reply_markup=kb.as_markup())
        return
    
    await callback.message.edit_text(
        f"Selected: {hour} hours\n"
        f"Now select minutes:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.startswith("fulltime_"))
async def process_exact_time(callback: CallbackQuery, state: FSMContext):
    """Handles exact time selection (hours:minutes)"""
    await callback.answer()
    
    # Extract time from callback_data
    time_str = callback.data.split("_")[1]
    
    # Get user data from state
    user_data = await state.get_data()
    date_str = user_data.get("date_str")
    task_name = user_data.get("task_name")
    
    # Form deadline string
    deadline_str = f"{date_str} {time_str}"
    
    user_id = callback.from_user.id
    
    # Check if we're editing an existing task
    is_editing = user_data.get("is_editing", False)
    
    if is_editing:
        # Edit existing task
        edit_task_id = user_data.get("edit_task_id")
        tasks[user_id][edit_task_id]["deadline"] = deadline_str
        
        await callback.message.edit_text(
            f"✅ Deadline for task \"{tasks[user_id][edit_task_id]['name']}\" "
            f"changed to {deadline_str}",
            reply_markup=get_task_keyboard(user_id, edit_task_id)
        )
    else:
        # Create new task
        if user_id not in tasks:
            tasks[user_id] = {}
        
        task_id = str(len(tasks[user_id]) + 1)
        
        tasks[user_id][task_id] = {
            "name": task_name,
            "deadline": deadline_str,
            "completed": False,
            "reminded": False,
            "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        await callback.message.edit_text(
            f"✅ Task \"{task_name}\" with deadline {deadline_str} added!\n"
            f"I will remind you 1 hour before the deadline.",
            reply_markup=get_task_keyboard(user_id)
        )
    
    # Reset state
    await state.clear()

# Inline button handlers
@dp.callback_query(F.data == "list_tasks")
async def process_list_tasks(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    if user_id not in tasks or not tasks[user_id]:
        await callback.message.edit_text(
            "You don't have any tasks yet. Add a new task using the button below.",
            reply_markup=get_task_keyboard(user_id)
        )
    else:
        await callback.message.edit_text(
            "📋 <b>Your tasks:</b>",
            reply_markup=get_task_keyboard(user_id),
            parse_mode="HTML"
        )

@dp.callback_query(F.data == "add_task")
async def process_add_task_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Enter the task name:")
    await state.set_state(TaskStates.waiting_for_task_name)

@dp.callback_query(F.data.startswith("view_"))
async def process_view_task(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    task_id = callback.data.split("_")[1]
    
    if user_id in tasks and task_id in tasks[user_id]:
        task = tasks[user_id][task_id]
        status = "✅ Completed" if task["completed"] else "⏳ In Progress"
        
        # Get deadline information
        deadline_text = task["deadline"]
        
        try:
            if len(deadline_text.split()) == 1:
                # Only date (add 23:59)
                deadline = datetime.strptime(f"{deadline_text} 23:59", "%d.%m.%Y %H:%M")
            else:
                deadline = datetime.strptime(deadline_text, "%d.%m.%Y %H:%M")
            
            # Calculate remaining time
            time_diff = deadline - datetime.now()
            
            if time_diff.total_seconds() < 0:
                time_status = "⚠️ <b>Deadline passed</b>"
            else:
                days = time_diff.days
                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if days > 0:
                    time_status = f"⏳ Remaining: {days} d. {hours} h. {minutes} min."
                elif hours > 0:
                    time_status = f"⏳ Remaining: {hours} h. {minutes} min."
                else:
                    time_status = f"⏳ Remaining: {minutes} min."
        except ValueError:
            time_status = ""
        
        await callback.message.edit_text(
            f"🔹 <b>{task['name']}</b>\n\n"
            f"Status: {status}\n"
            f"Deadline: {task['deadline']}\n"
            f"{time_status}\n"
            f"Created: {task['created_at']}",
            reply_markup=get_task_keyboard(user_id, task_id),
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("complete_"))
async def process_complete_task(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = callback.data.split("_")[1]
    
    if user_id in tasks and task_id in tasks[user_id]:
        # Toggle task status
        tasks[user_id][task_id]["completed"] = not tasks[user_id][task_id]["completed"]
        status = "completed" if tasks[user_id][task_id]["completed"] else "not completed"
        
        await callback.answer(f"Task marked as {status}")
        
        # Update message
        task = tasks[user_id][task_id]
        status_text = "✅ Completed" if task["completed"] else "⏳ In Progress"
        
        # Get deadline information
        deadline_text = task["deadline"]
        time_status = ""
        
        if not task["completed"]:
            try:
                if len(deadline_text.split()) == 1:
                    # Only date (add 23:59)
                    deadline = datetime.strptime(f"{deadline_text} 23:59", "%d.%m.%Y %H:%M")
                else:
                    deadline = datetime.strptime(deadline_text, "%d.%m.%Y %H:%M")
                
                # Calculate remaining time
                time_diff = deadline - datetime.now()
                
                if time_diff.total_seconds() < 0:
                    time_status = "⚠️ <b>Deadline passed</b>"
                else:
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    if days > 0:
                        time_status = f"⏳ Remaining: {days} d. {hours} h. {minutes} min."
                    elif hours > 0:
                        time_status = f"⏳ Remaining: {hours} h. {minutes} min."
                    else:
                        time_status = f"⏳ Remaining: {minutes} min."
            except ValueError:
                time_status = ""
        
        await callback.message.edit_text(
            f"🔹 <b>{task['name']}</b>\n\n"
            f"Status: {status_text}\n"
            f"Deadline: {task['deadline']}\n"
            f"{time_status}\n"
            f"Created: {task['created_at']}",
            reply_markup=get_task_keyboard(user_id, task_id),
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("delete_"))
async def process_delete_task(callback: CallbackQuery):
    user_id = callback.from_user.id
    task_id = callback.data.split("_")[1]
    
    if user_id in tasks and task_id in tasks[user_id]:
        task_name = tasks[user_id][task_id]["name"]
        # Delete task
        del tasks[user_id][task_id]
        
        await callback.answer(f"Task \"{task_name}\" deleted")
        
        # Return to task list
        if tasks[user_id]:
            await callback.message.edit_text(
                "📋 <b>Your tasks:</b>",
                reply_markup=get_task_keyboard(user_id),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                "You don't have any tasks yet. Add a new task using the button below.",
                reply_markup=get_task_keyboard(user_id)
            )

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_task(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    task_id = callback.data.split("_")[1]
    
    if user_id in tasks and task_id in tasks[user_id]:
        kb = InlineKeyboardBuilder()
        kb.button(text="Edit Name", callback_data=f"edit_name_{task_id}")
        kb.button(text="Edit Deadline", callback_data=f"edit_deadline_{task_id}")
        kb.button(text="« Back", callback_data=f"view_{task_id}")
        kb.adjust(1)
        
        await callback.message.edit_text(
            "Select what you want to edit:",
            reply_markup=kb.as_markup()
        )

@dp.callback_query(F.data.startswith("edit_name_"))
async def process_edit_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_id = callback.data.split("_")[2]
    
    await state.update_data(edit_task_id=task_id)
    await callback.message.edit_text("Enter new task name:")
    await state.set_state(TaskStates.waiting_for_edit_name)

@dp.message(TaskStates.waiting_for_edit_name)
async def process_edit_name_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    task_id = user_data["edit_task_id"]
    
    if user_id in tasks and task_id in tasks[user_id]:
        # Update task name
        tasks[user_id][task_id]["name"] = message.text.strip()
        
        await message.answer(
            f"✅ Task name updated to \"{message.text.strip()}\"",
            reply_markup=get_task_keyboard(user_id, task_id)
        )
        
        await state.clear()

@dp.callback_query(F.data.startswith("edit_deadline_"))
async def process_edit_deadline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_id = callback.data.split("_")[2]
    
    await state.update_data(edit_task_id=task_id)
    
    # Save flag that we're editing an existing task
    await state.update_data(is_editing=True)
    
    # Redirect to month selection
    await callback.message.edit_text(
        "Select Month:",
        reply_markup=get_month_keyboard()
    )
    await state.set_state(TaskStates.waiting_for_date_selection)

@dp.callback_query(F.data == "hide_calendar")
async def process_hide_calendar(callback: CallbackQuery):
    """Hides the calendar"""
    await callback.answer("Calendar hidden")
    await callback.message.delete()

@dp.callback_query(F.data == "time_all_day")
async def process_time_all_day(callback: CallbackQuery, state: FSMContext):
    """Handles 'All Day' selection"""
    await callback.answer()
    
    # Get user data
    user_data = await state.get_data()
    date_str = user_data.get("date_str")
    
    # Form deadline string
    deadline_str = date_str  # Only date without time
    
    user_id = callback.from_user.id
    
    # Initialize dictionary for user if it doesn't exist yet
    if user_id not in tasks:
        tasks[user_id] = {}
    
    # Check if we're editing an existing task
    is_editing = user_data.get("is_editing", False)
    
    if is_editing:
        # Edit existing task
        edit_task_id = user_data.get("edit_task_id")
        tasks[user_id][edit_task_id]["deadline"] = deadline_str
        
        await callback.message.edit_text(
            f"✅ Deadline for task \"{tasks[user_id][edit_task_id]['name']}\" "
            f"changed to {deadline_str}",
            reply_markup=get_task_keyboard(user_id, edit_task_id)
        )
    else:
        # Generate unique ID for the task
        task_id = str(len(tasks[user_id]) + 1)
        
        # Add task
        tasks[user_id][task_id] = {
            "name": user_data.get("task_name"),
            "deadline": deadline_str,
            "completed": False,
            "reminded": False,
            "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        await callback.message.edit_text(
            f"✅ Task \"{user_data.get('task_name')}\" with deadline {deadline_str} added!\n"
            f"I will remind you 1 hour before the deadline.",
            reply_markup=get_task_keyboard(user_id)
        )
    
    # Reset state
    await state.clear()

@dp.callback_query(F.data == "custom_minute")
async def process_custom_minute(callback: CallbackQuery):
    """Stub for old function - redirect back to time selection"""
    await callback.answer("This function is no longer available")
    await process_back_to_time(callback)

@dp.callback_query(F.data == "back_to_time")
async def process_back_to_time(callback: CallbackQuery, state: FSMContext):
    """Return to time selection"""
    await callback.answer()
    
    # Get user data
    user_data = await state.get_data()
    day = int(user_data.get("selected_day"))
    month = int(user_data.get("selected_month"))
    year = int(user_data.get("selected_year"))
    
    # Form string with new callback_data
    callback_data = f"day_{day}_{month}_{year}"
    
    # Update callback.data
    callback.data = callback_data
    
    # Call day selection handler
    await process_day_selection(callback, state)

# Add a handler for ignoring clicks on weekdays and empty cells
@dp.callback_query(F.data == "ignore")
async def process_ignore_button(callback: CallbackQuery):
    """Ignores clicks on weekday headers and empty cells"""
    await callback.answer()

# Function for starting background tasks
async def start_background_tasks():
    # Start deadline checking in the background
    asyncio.create_task(check_deadlines())

# Bot startup
async def main():
    logging.info("Bot started")
    # Start background tasks
    await start_background_tasks()
    # Start the bot
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 