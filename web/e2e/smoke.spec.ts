import { test, expect } from '@playwright/test';

test.describe('Horse Racing App E2E', () => {
  test('should load the home page and display races', async ({ page }) => {
    // Note: E2E tests require backend and web server to be running.
    // We assume the app is running locally for this smoke test.
    await page.goto('/');
    
    // Check if the title is present (assuming "Home" or "Races")
    await expect(page).toHaveTitle(/Horse Racing Prediction/);

    // Verify track filters exist
    const seoulTrack = page.locator('text=Seoul');
    await expect(seoulTrack).toBeVisible();
  });

  test('should navigate to login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h2')).toContainText('Login');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });
});
