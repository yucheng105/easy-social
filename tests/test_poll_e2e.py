from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from easy_social import create_app
from easy_social.extensions import db
from easy_social.models import Comment, PollOption, PollVote, Post, User

selenium = pytest.importorskip("selenium")

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.fixture(scope="module")
def ui_app():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp_path / 'poll_ui.sqlite'}",
                "UPLOAD_FOLDER": str(temp_path / "uploads"),
                "MEDIA_STORAGE_BACKEND": "local",
                "WTF_CSRF_ENABLED": False,
            }
        )
        with app.app_context():
            db.create_all()
        yield app


@pytest.fixture(scope="module")
def live_server(ui_app):
    try:
        server = make_server("127.0.0.1", 0, ui_app, threaded=True)
    except SystemExit:
        pytest.skip("Selenium live server could not bind to a local port")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}"

    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def browser():
    browser_name = os.environ.get("SELENIUM_BROWSER", "chrome").lower()
    headless = os.environ.get("SELENIUM_HEADLESS", "1") != "0"

    try:
        if browser_name == "firefox":
            options = webdriver.FirefoxOptions()
            if headless:
                options.add_argument("-headless")
            driver = webdriver.Firefox(options=options)
        else:
            options = webdriver.ChromeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--window-size=1280,900")
            driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        pytest.skip(f"Selenium browser could not start: {exc.msg}")

    yield driver

    driver.quit()


@pytest.fixture(autouse=True)
def clean_database(ui_app):
    with ui_app.app_context():
        db.session.query(PollVote).delete()
        db.session.query(PollOption).delete()
        db.session.query(Comment).delete()
        db.session.query(Post).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture()
def poll_user(ui_app):
    with ui_app.app_context():
        user = User(username="testuser", email="testuser@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()


def wait_for_text(browser, text: str):
    WebDriverWait(browser, 5).until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), text))


def wait_for_feed(browser):
    WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "form.composer")))
    wait_for_text(browser, "Feed")


def set_field_value(browser, field, value: str):
    browser.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
        """,
        field,
        value,
    )


def submit_form(browser, form):
    browser.execute_script("arguments[0].requestSubmit ? arguments[0].requestSubmit() : arguments[0].submit();", form)


@pytest.mark.ui
def test_user_poll_interaction_lifecycle(browser, live_server, poll_user):
    browser.get(f"{live_server}/auth/login")
    login_form = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "form.form-stack"))
    )
    set_field_value(browser, login_form.find_element(By.NAME, "username_or_email"), "testuser")
    set_field_value(browser, login_form.find_element(By.NAME, "password"), "password123")
    submit_form(browser, login_form)
    wait_for_feed(browser)

    composer = browser.find_element(By.CSS_SELECTOR, "form.composer")
    composer.find_element(By.CSS_SELECTOR, "[data-poll-toggle]").click()
    WebDriverWait(browser, 5).until(lambda _: composer.find_element(By.CSS_SELECTOR, "[data-poll-panel]").is_displayed())

    set_field_value(browser, composer.find_element(By.NAME, "body"), "Which feature should ship next?")
    poll_inputs = composer.find_elements(By.CSS_SELECTOR, "input[name='options']")
    assert len(poll_inputs) == 4
    set_field_value(browser, poll_inputs[0], "Better notifications")
    set_field_value(browser, poll_inputs[1], "Profile themes")
    submit_form(browser, composer)

    wait_for_text(browser, "Which feature should ship next?")
    poll_card = WebDriverWait(browser, 5).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-poll-card]"))
    )
    assert poll_card.find_element(By.CSS_SELECTOR, "[data-poll-state]").text == "0 total votes"
    assert poll_card.find_element(By.CSS_SELECTOR, "[data-poll-option-results]").is_displayed()
    assert poll_card.find_element(By.CSS_SELECTOR, "[data-poll-option-percentage]").text == "0.0"

    vote_buttons = poll_card.find_elements(By.CSS_SELECTOR, "button.poll-option")
    assert len(vote_buttons) == 2
    vote_buttons[0].click()

    WebDriverWait(browser, 5).until(
        lambda _: poll_card.find_element(By.CSS_SELECTOR, "[data-poll-state]").text == "1 total votes"
    )
    WebDriverWait(browser, 5).until(
        lambda _: poll_card.find_element(By.CSS_SELECTOR, "[data-poll-option-results]").is_displayed()
    )

    assert all(button.get_attribute("disabled") for button in vote_buttons)
    assert poll_card.find_element(By.CSS_SELECTOR, "[data-poll-option-percentage]").text == "100"
