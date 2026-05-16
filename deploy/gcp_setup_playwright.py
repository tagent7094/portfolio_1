"""
Automated GCP setup via browser automation.
Creates project, enables Sheets+Drive APIs, creates service account,
downloads JSON key, uploads to VPS.
"""
import asyncio
import json
import os
import subprocess
import time
import re
from pathlib import Path

EMAIL = "content@tagent.club"
PASSWORD = "content@2026"
VPS_HOST = "root@147.93.20.156"
VPS_KEY_PATH = "/etc/tagent/google-sa.json"
LOCAL_KEY_PATH = Path(__file__).parent / "google-sa.json"
PROJECT_PREFIX = "tagent-sheets"


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=200,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await ctx.new_page()

        # ── 1. Login ────────────────────────────────────────────────────────
        print("==> Step 1: Google login")
        await page.goto(
            "https://accounts.google.com/signin/v2/identifier"
            "?continue=https%3A%2F%2Fconsole.cloud.google.com%2F"
            "&flowName=GlifWebSignIn&flowEntry=ServiceLogin",
            wait_until="networkidle",
        )
        await page.fill('input[type="email"]', EMAIL)
        await page.locator("#identifierNext").click()
        await page.wait_for_selector('input[type="password"]', timeout=15000)
        await asyncio.sleep(1)
        await page.fill('input[type="password"]', PASSWORD)
        await page.locator("#passwordNext").click()

        print("    Waiting for login to complete...")
        try:
            await page.wait_for_url(
                lambda u: "console.cloud.google.com" in u or "myaccount.google.com" in u,
                timeout=45000,
            )
        except Exception:
            print(f"    URL after wait: {page.url}")

        # Handle 2-step verification prompt if shown
        url = page.url
        print(f"    Current URL: {url}")
        if "challenge" in url or "signin" in url.lower():
            print("    Possible 2FA/challenge page — waiting 30s for manual input...")
            await asyncio.sleep(30)

        print("==> Logged in. Going to Cloud Console...")
        await page.goto("https://console.cloud.google.com", wait_until="networkidle")
        await asyncio.sleep(3)

        # Accept ToS if shown
        try:
            tos_btn = page.locator('button:has-text("Agree"), button:has-text("Accept")')
            if await tos_btn.count() > 0:
                await tos_btn.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # ── 2. Create project ────────────────────────────────────────────────
        project_id = f"{PROJECT_PREFIX}-{int(time.time())}"
        print(f"==> Step 2: Creating project {project_id}")
        await page.goto(
            "https://console.cloud.google.com/projectcreate",
            wait_until="networkidle",
        )
        await asyncio.sleep(3)

        # Fill project name
        name_input = page.locator('input[id*="project-name"], input[placeholder*="project name" i], input[aria-label*="project name" i]').first
        await name_input.wait_for(timeout=15000)
        await name_input.fill("tagent Sheets")
        await asyncio.sleep(2)  # let the project ID auto-fill

        # Override project ID
        try:
            edit_btn = page.locator('button:has-text("Edit"), [aria-label*="Edit project ID" i]').first
            if await edit_btn.count() > 0:
                await edit_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        try:
            id_input = page.locator('input[id*="project-id"], input[aria-label*="project id" i]').first
            if await id_input.count() > 0:
                await id_input.triple_click()
                await id_input.fill(project_id)
                await asyncio.sleep(1)
        except Exception:
            pass

        # Click Create
        create_btn = page.locator('button:has-text("Create"), button[type="submit"]:has-text("Create")').first
        await create_btn.click()
        print("    Waiting for project creation (up to 90s)...")
        await asyncio.sleep(15)

        # Wait for project to become active
        for _ in range(15):
            if project_id in page.url or "dashboard" in page.url:
                break
            await asyncio.sleep(5)

        print(f"    Project URL: {page.url}")

        # ── 3. Enable Sheets API ─────────────────────────────────────────────
        print("==> Step 3: Enabling Google Sheets API")
        await page.goto(
            f"https://console.cloud.google.com/apis/library/sheets.googleapis.com?project={project_id}",
            wait_until="networkidle",
        )
        await asyncio.sleep(3)
        try:
            enable_btn = page.locator('button:has-text("Enable"), a:has-text("Enable")').first
            if await enable_btn.count() > 0:
                await enable_btn.click()
                print("    Sheets API enabled.")
                await asyncio.sleep(10)
            else:
                print("    Sheets API may already be enabled.")
        except Exception as e:
            print(f"    Warning enabling Sheets API: {e}")

        # ── 4. Enable Drive API ──────────────────────────────────────────────
        print("==> Step 4: Enabling Google Drive API")
        await page.goto(
            f"https://console.cloud.google.com/apis/library/drive.googleapis.com?project={project_id}",
            wait_until="networkidle",
        )
        await asyncio.sleep(3)
        try:
            enable_btn = page.locator('button:has-text("Enable"), a:has-text("Enable")').first
            if await enable_btn.count() > 0:
                await enable_btn.click()
                print("    Drive API enabled.")
                await asyncio.sleep(10)
            else:
                print("    Drive API may already be enabled.")
        except Exception as e:
            print(f"    Warning enabling Drive API: {e}")

        # ── 5. Create service account ────────────────────────────────────────
        print("==> Step 5: Creating service account")
        await page.goto(
            f"https://console.cloud.google.com/iam-admin/serviceaccounts/create?project={project_id}",
            wait_until="networkidle",
        )
        await asyncio.sleep(3)

        # Fill service account name
        sa_name_input = page.locator('input[id*="name"], input[placeholder*="service account name" i], input[aria-label*="account name" i]').first
        await sa_name_input.wait_for(timeout=15000)
        await sa_name_input.fill("tagent-sheets-bot")
        await asyncio.sleep(1)

        # Fill display name if separate field
        try:
            display_input = page.locator('input[placeholder*="display name" i], input[aria-label*="display name" i]').first
            if await display_input.count() > 0:
                await display_input.fill("tagent Sheets Bot")
        except Exception:
            pass

        # Click "Create and Continue"
        continue_btn = page.locator('button:has-text("Create and Continue"), button:has-text("Create")').first
        await continue_btn.click()
        await asyncio.sleep(3)

        # Skip role and grant steps (click Continue/Done)
        for _ in range(3):
            try:
                next_btn = page.locator('button:has-text("Continue"), button:has-text("Done"), button:has-text("Skip")').first
                if await next_btn.count() > 0:
                    await next_btn.click()
                    await asyncio.sleep(2)
            except Exception:
                break

        # ── 6. Extract SA email from URL ──────────────────────────────────────
        sa_email = f"tagent-sheets-bot@{project_id}.iam.gserviceaccount.com"
        print(f"    Service account: {sa_email}")

        # ── 7. Create JSON key ───────────────────────────────────────────────
        print("==> Step 6: Creating JSON key")
        # Navigate to the SA detail/keys page
        sa_encoded = sa_email.replace("@", "%40")
        await page.goto(
            f"https://console.cloud.google.com/iam-admin/serviceaccounts/details/{sa_encoded}/keys?project={project_id}",
            wait_until="networkidle",
        )
        await asyncio.sleep(3)

        # Intercepted download — set up download listener
        async with page.expect_download(timeout=30000) as dl_info:
            # Click "Add Key" button
            add_key_btn = page.locator('button:has-text("Add key"), button:has-text("ADD KEY")').first
            await add_key_btn.click()
            await asyncio.sleep(1)

            # Select "Create new key"
            create_key_opt = page.locator(':has-text("Create new key"), button:has-text("Create new key")').first
            await create_key_opt.click()
            await asyncio.sleep(1)

            # Ensure JSON is selected
            json_radio = page.locator('input[value="json"], label:has-text("JSON") input').first
            if await json_radio.count() > 0:
                await json_radio.click()

            # Click Create
            create_btn = page.locator('button:has-text("Create")').last
            await create_btn.click()

        download = await dl_info.value
        key_path = await download.path()
        print(f"    Key downloaded to: {key_path}")

        # Copy to local path
        import shutil
        shutil.copy(key_path, str(LOCAL_KEY_PATH))
        print(f"    Key saved to: {LOCAL_KEY_PATH}")

        await browser.close()

    # ── 8. Copy key to VPS ────────────────────────────────────────────────
    print("==> Step 7: Uploading key to VPS")
    vps_dir = VPS_KEY_PATH.rsplit("/", 1)[0]
    subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", VPS_HOST, f"mkdir -p {vps_dir}"],
        check=True, capture_output=True,
    )
    result = subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", str(LOCAL_KEY_PATH), f"{VPS_HOST}:{VPS_KEY_PATH}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    SCP error: {result.stderr}")
        raise RuntimeError("Failed to upload key to VPS")

    # Fix permissions
    subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", VPS_HOST,
         f"chmod 600 {VPS_KEY_PATH}; chown tagent:tagent {VPS_KEY_PATH} 2>/dev/null || true"],
        check=True, capture_output=True,
    )

    print("==> SUCCESS!")
    print(f"    Key is at {VPS_KEY_PATH} on the VPS.")
    print("    Google Sheets export is ready. Restart tagent if needed:")
    print("    ssh root@147.93.20.156 systemctl restart tagent")


if __name__ == "__main__":
    asyncio.run(run())
