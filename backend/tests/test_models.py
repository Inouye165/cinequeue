import pytest
from app.models import days_label

def test_days_label():
    # TBA case
    assert days_label(None) == "Date TBA"
    
    # Already released (hides countdown badge)
    assert days_label(-1) == ""
    assert days_label(-100) == ""
    
    # Today / Tomorrow
    assert days_label(0) == "Out today"
    assert days_label(1) == "1 day away"
    
    # Days countdown (under a week)
    assert days_label(5) == "5 days away"
    
    # Week and days (7 to 13 days)
    assert days_label(7) == "1 week away"
    assert days_label(9) == "1 week 2 days away"
    assert days_label(13) == "1 week 6 days away"
    
    # Weeks only (14 to 29 days)
    assert days_label(14) == "2 weeks away"
    assert days_label(23) == "3 weeks away"
    assert days_label(29) == "4 weeks away"
    
    # Months only (30+ days)
    assert days_label(30) == "1 month away"
    assert days_label(45) == "1 month away"
    assert days_label(60) == "2 months away"
    assert days_label(365) == "12 months away"
