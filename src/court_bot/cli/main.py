"""
Court Bot — Command Line Interface.

Beautiful CLI powered by Typer + Rich with:
  - Interactive config wizard
  - Live booking status display
  - Multiple commands: run, slots, list, cancel, config
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

# Fix encoding for CJK output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich import box

from court_bot import __version__
from court_bot.core.config import load_config, generate_example_config, AppConfig
from court_bot.core.scheduler import BookingScheduler
from court_bot.platforms import get_platform
from court_bot.utils.logger import setup_logging

app = typer.Typer(
    name="court-bot",
    help="🏸 Automated sports court booking bot",
    add_completion=False,
)
console = Console()

BANNER = r"""
   ██████╗ ██████╗ ██╗   ██╗██████╗ ████████╗    ██████╗  ██████╗ ████████╗
  ██╔════╝██╔═══██╗██║   ██║██╔══██╗╚══██╔══╝    ██╔══██╗██╔═══██╗╚══██╔══╝
  ██║     ██║   ██║██║   ██║██████╔╝   ██║       ██████╔╝██║   ██║   ██║
  ██║     ██║   ██║██║   ██║██╔══██╗   ██║       ██╔══██╗██║   ██║   ██║
  ╚██████╗╚██████╔╝╚██████╔╝██║  ██║   ██║       ██████╔╝╚██████╔╝   ██║
   ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝   ╚═╝       ╚═════╝  ╚═════╝   ╚═╝
"""


# ── Global options ───────────────────────────────────────

@app.callback()
def main(
    ctx: typer.Context,
    config_path: Path = typer.Option(
        Path("config/config.yaml"),
        "--config", "-c",
        help="Path to configuration file",
        exists=False,
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable debug logging",
    ),
):
    """Court Bot helps you automatically book sports courts."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose
    ctx.obj["log_level"] = "DEBUG" if verbose else "INFO"


# ── Commands ─────────────────────────────────────────────

@app.command()
def run(
    ctx: typer.Context,
    now: bool = typer.Option(
        False, "--now", help="Book immediately without waiting for opening time",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch slots but don't submit booking",
    ),
    date: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Target date (YYYY-MM-DD). Overrides date_offset in config.",
    ),
    target_day: Optional[str] = typer.Option(
        None, "--target-day",
        help='Target day of week. E.g. "Friday", "星期五". Overrides date_offset.',
    ),
    times: Optional[str] = typer.Option(
        None, "--times", "-t",
        help='Preferred time slots, comma-separated. E.g. "18:30-20:30,19:30-20:30"',
    ),
    courts: Optional[str] = typer.Option(
        None, "--courts", "-n",
        help='Preferred court numbers, comma-separated. E.g. "6,7,8,9,10"',
    ),
):
    """
    Start the booking scheduler.

    Examples:
        court-bot run                                    # Use config defaults
        court-bot run --date 2026-06-20 --times "18:30-20:30" --courts "6,7,8"
        court-bot run --now --dry-run                    # Test immediately
        court-bot run --target-day Friday --now           # Book next Friday now
    """
    _print_banner()

    config = _load_or_exit(ctx)
    if dry_run:
        config.advanced.dry_run = True

    # ── CLI overrides ───────────────────────────────────
    if times:
        config.booking.preferred_times = [t.strip() for t in times.split(",")]
    if courts:
        config.booking.preferred_courts = [int(n.strip()) for n in courts.split(",")]
    if target_day:
        config.booking.target_day_of_week = target_day
    if date:
        from datetime import date as dt, timedelta
        target = dt.fromisoformat(date)
        offset = (target - dt.today()).days
        config.booking.date_offset = max(0, offset)
        config.booking.target_day_of_week = ""  # date overrides day-of-week

    platform_cls = _get_platform_or_exit(config.platform)
    platform = platform_cls(config)

    try:
        scheduler = BookingScheduler(config, platform)
        result = scheduler.run(fire_immediately=now)

        if result and result.success:
            _success_panel(result)
            raise typer.Exit(0)
        else:
            _failure_panel()
            raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
        raise typer.Exit(130)
    finally:
        if hasattr(platform, "close"):
            platform.close()


@app.command()
def slots(
    ctx: typer.Context,
    date: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Date to query (YYYY-MM-DD). Defaults to tomorrow.",
    ),
):
    """
    Show available courts and time slots.
    """
    _print_banner()
    config = _load_or_exit(ctx)
    platform_cls = _get_platform_or_exit(config.platform)
    platform = platform_cls(config)

    try:
        if not platform.authenticate():
            console.print("[red]❌ Authentication failed[/red]")
            raise typer.Exit(1)

        from datetime import datetime, timedelta
        if date is None:
            # Support target_day_of_week for default date calculation
            day_of_week = config.booking.target_day_of_week.strip().lower()
            if day_of_week:
                from court_bot.core.scheduler import BookingScheduler
                day_map = BookingScheduler._DAY_MAP
                if day_of_week in day_map:
                    target_dow = day_map[day_of_week]
                    today = datetime.now()
                    today_dow = today.weekday()
                    days_ahead = target_dow - today_dow
                    if days_ahead <= 0:
                        days_ahead += 7
                    date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                else:
                    date = (datetime.now() + timedelta(days=config.booking.date_offset)).strftime("%Y-%m-%d")
            else:
                date = (datetime.now() + timedelta(days=config.booking.date_offset)).strftime("%Y-%m-%d")

        console.print(f"\n📅 Querying slots for [bold cyan]{date}[/bold cyan]...\n")

        candidates = platform.find_candidates(
            date=date,
            court_type=config.booking.court_type,
            preferred_courts=config.booking.preferred_courts,
            preferred_times=config.booking.preferred_times,
            fallback_to_any=True,
            max_candidates=config.booking.max_candidates,
        )

        if not candidates:
            console.print("[yellow]No available slots found.[/yellow]")
            console.print("[dim]Try a different date or check your configuration.[/dim]")
            return

        table = Table(title=f"Available Slots — {date}", box=box.ROUNDED)
        table.add_column("#", style="dim", width=4)
        table.add_column("Court", style="cyan")
        table.add_column("Time", style="green")
        table.add_column("Court ID", style="dim")
        table.add_column("Slot ID", style="dim")

        for i, c in enumerate(candidates, 1):
            table.add_row(
                str(i), c.court_name, c.slot_label,
                c.court_id, c.slot_id,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(candidates)} available slot(s)[/dim]")

    finally:
        if hasattr(platform, "close"):
            platform.close()


@app.command()
def list_bookings(ctx: typer.Context):
    """Show your existing reservations."""
    _print_banner()
    config = _load_or_exit(ctx)
    platform_cls = _get_platform_or_exit(config.platform)
    platform = platform_cls(config)

    try:
        if not platform.authenticate():
            console.print("[red]❌ Authentication failed[/red]")
            raise typer.Exit(1)

        bookings = getattr(platform, "get_my_bookings", lambda: [])()
        if not bookings:
            console.print("[yellow]📋 No existing bookings[/yellow]")
            return

        console.print(f"\n📋 [bold]Your Bookings ({len(bookings)})[/bold]\n")
        for b in bookings:
            console.print(f"  {b}")

    finally:
        if hasattr(platform, "close"):
            platform.close()


@app.command()
def cancel(
    ctx: typer.Context,
    booking_id: str = typer.Argument(..., help="Booking ID to cancel"),
):
    """Cancel a specific booking by ID."""
    _print_banner()
    config = _load_or_exit(ctx)
    platform_cls = _get_platform_or_exit(config.platform)
    platform = platform_cls(config)

    try:
        if not platform.authenticate():
            console.print("[red]❌ Authentication failed[/red]")
            raise typer.Exit(1)

        ok = getattr(platform, "cancel_booking", lambda _: False)(booking_id)
        if ok:
            console.print(f"[green]✅ Cancelled: {booking_id}[/green]")
        else:
            console.print(f"[red]❌ Failed to cancel: {booking_id}[/red]")
            raise typer.Exit(1)
    finally:
        if hasattr(platform, "close"):
            platform.close()


@app.command()
def init_config(
    output: Path = typer.Option(
        Path("config/config.yaml"),
        "--output", "-o",
        help="Where to write the example config file",
    ),
):
    """
    Generate an example configuration file.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    example = generate_example_config()

    if output.exists():
        overwrite = typer.confirm(
            f"{output} already exists. Overwrite?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Aborted.[/yellow]")
            return

    output.write_text(example, encoding="utf-8")
    console.print(f"[green]✅ Example config written to {output}[/green]")
    console.print("[dim]Edit this file with your account details and preferences.[/dim]")


@app.command()
def schedule_setup(
    ctx: typer.Context,
    run_day: str = typer.Option(
        "Thursday", "--run-day",
        help='Day to run the scheduler. E.g. "Thursday", "星期四"',
    ),
    run_time: str = typer.Option(
        "07:00", "--run-time",
        help='Time to run (HH:MM). Default: 07:00',
    ),
    target_day: str = typer.Option(
        "Friday", "--target-day",
        help='Target booking day. E.g. "Friday", "星期五"',
    ),
    python_path: Optional[str] = typer.Option(
        None, "--python", "-p",
        help="Path to Python interpreter. Auto-detect if omitted.",
    ),
    install: bool = typer.Option(
        True, "--install/--no-install",
        help="Create the scheduled task (default: true)",
    ),
):
    """
    Set up a Windows scheduled task for automatic booking.

    Example:
        court-bot schedule-setup                                    # Thursday 7AM → Friday
        court-bot schedule-setup --run-day 周四 --run-time 06:30     # Custom schedule
    """
    import subprocess
    import shutil

    _print_banner()

    # Resolve paths
    config_path = ctx.obj["config_path"].resolve()
    if not config_path.exists():
        console.print(f"[red]❌ Config not found: {config_path}[/red]")
        console.print("[yellow]Run 'court-bot init-config' first.[/yellow]")
        raise typer.Exit(1)

    # Find Python
    if python_path:
        py = python_path
    else:
        py = shutil.which("python") or shutil.which("python3") or sys.executable
    console.print(f"Python: [dim]{py}[/dim]")

    # Find court-bot executable
    cb = shutil.which("court-bot") or shutil.which("court-bot.exe")
    if cb:
        exe_cmd = f'"{cb}"'
    else:
        exe_cmd = f'"{py}" -m court_bot.cli.main'

    # Build the full command
    run_cmd = (
        f'{exe_cmd} run '
        f'--config "{config_path}" '
        f'--target-day "{target_day}" '
        f'--now'
    )
    task_name = "CourtBot_AutoBook"

    console.print(f"Task name:    [bold cyan]{task_name}[/bold cyan]")
    console.print(f"Schedule:     [bold]Every {run_day} at {run_time}[/bold]")
    console.print(f"Target:       [bold green]Next {target_day}[/bold green]")
    console.print(f"Config:       [dim]{config_path}[/dim]")
    console.print(f"Command:      [dim]{run_cmd}[/dim]")

    if not install:
        console.print("\n[yellow]--no-install: skipping task creation[/yellow]")
        return

    # Build PowerShell script for scheduled task
    ps_script = f'''
$taskName = "{task_name}"
$action = New-ScheduledTaskAction -Execute "{py}" -Argument '-c "{run_cmd}"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {run_day.split(",")[0]} -At "{run_time}:00"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$task = Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
if ($task) {{
    Write-Host "✅ Scheduled task '$taskName' created successfully!"
    Write-Host "   Schedule: Every {run_day} at {run_time}:00"
    Write-Host "   You can verify in: taskschd.msc"
}} else {{
    Write-Host "❌ Failed to create task"
}}
'''

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            console.print(f"\n[green]{result.stdout.strip()}[/green]")
            console.print("\n[bold]Setup complete! 🎉[/bold]")
            console.print(
                f"The bot will auto-book [cyan]{target_day}[/cyan] courts "
                f"every [cyan]{run_day}[/cyan] at [cyan]{run_time}[/cyan]."
            )
            console.print("[dim]Manage tasks: taskschd.msc[/dim]")
        else:
            console.print(f"\n[red]Error: {result.stderr or result.stdout}[/red]")
            console.print("\n[yellow]Manual setup (run this in PowerShell as Admin):[/yellow]")
            console.print(ps_script, markup=False)
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]❌ Task creation timed out[/red]")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print("[red]❌ PowerShell not found[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version and exit."""
    console.print(f"Court Bot v{__version__}")


# ── Helpers ──────────────────────────────────────────────

def _print_banner() -> None:
    console.print(Text(BANNER, style="bold cyan"))
    console.print(f"  {'─' * 75}")
    console.print(f"  Automated Court Booking  ·  v{__version__}")
    console.print(f"  {'─' * 75}\n")


def _load_or_exit(ctx: typer.Context) -> AppConfig:
    """Load config or exit with a helpful message."""
    config_path = ctx.obj["config_path"]

    # Set up logging first (to a temp file if no config yet)
    log_file = setup_logging(ctx.obj["log_level"])

    if not config_path.exists():
        console.print(f"[red]❌ Config not found: {config_path}[/red]")
        console.print(f"\n[yellow]Run this to generate an example config:[/yellow]")
        console.print(f"  court-bot init-config\n")
        raise typer.Exit(1)

    try:
        return load_config(str(config_path))
    except Exception as e:
        console.print(f"[red]❌ Failed to load config: {e}[/red]")
        raise typer.Exit(1)


def _get_platform_or_exit(platform_name: str):
    """Resolve platform class or exit with error."""
    try:
        return get_platform(platform_name)
    except KeyError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)


def _success_panel(result) -> None:
    text = Text()
    text.append("🎉 Booking Successful!\n\n", style="bold green")
    text.append(f"  Court:    {result.court_name}\n")
    text.append(f"  Time:     {result.slot_label}\n")
    text.append(f"  ID:       {result.booking_id}\n")
    console.print(Panel(text, border_style="green", title="Success"))


def _failure_panel() -> None:
    text = Text()
    text.append("❌ Booking Failed\n\n", style="bold red")
    text.append("All candidates were attempted but none succeeded.\n")
    text.append("Check the logs for details and try again.\n")
    console.print(Panel(text, border_style="red", title="Failed"))


# ── Entry point ──────────────────────────────────────────

def main_cli():
    """Entry point for console_scripts."""
    app()


if __name__ == "__main__":
    main_cli()
