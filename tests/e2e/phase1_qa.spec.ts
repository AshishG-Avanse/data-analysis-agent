import { test, expect } from '@playwright/test'
import path from 'path'

const FIXTURE_CSV = path.join(__dirname, 'fixtures', 'tiny.csv')

test.describe('Phase 1 — upload, ask, answer', () => {
  test('upload a file, ask a question, view the code, see Phase 2 stubs', async ({ page }) => {
    await page.goto('/app/')

    // 1. Upload a real small CSV file.
    const fileInput = page.getByTestId('file-input')
    await fileInput.setInputFiles(FIXTURE_CSV)

    // 2. Assert the schema readout appears — row count, column names visible in the DOM.
    const schemaSummary = page.getByTestId('schema-summary')
    await expect(schemaSummary).toBeVisible({ timeout: 15_000 })
    await expect(schemaSummary).toContainText('5 rows')
    await expect(schemaSummary).toContainText('product')
    await expect(schemaSummary).toContainText('region')
    await expect(schemaSummary).toContainText('revenue')

    // 3. Ask a plain-English question.
    const questionInput = page.getByTestId('question-input')
    await questionInput.fill('What is the total revenue?')
    await page.getByTestId('question-submit').click()

    // 4. Wait for the spinner to appear then disappear, and assert a real
    // plain-language answer renders — not just a 200/empty check.
    const spinner = page.getByTestId('answer-spinner')
    await expect(spinner).toBeVisible({ timeout: 5_000 })
    await expect(spinner).toHaveCount(0, { timeout: 60_000 })

    const answerText = page.getByTestId('answer-text')
    await expect(answerText).toBeVisible()
    const answerContent = await answerText.textContent()
    expect(answerContent?.trim().length).toBeGreaterThan(0)

    // 5. Click "View code" and assert the code block reveals real Python-looking content.
    await page.getByRole('button', { name: /view code/i }).click()
    const codeBlock = page.locator('pre code')
    await expect(codeBlock).toBeVisible()
    const codeContent = await codeBlock.textContent()
    expect(codeContent).toMatch(/def |import |\bdf\b/)

    // 6. Assert the three labelled Phase-2 stub placeholders are visible and readable.
    await expect(page.getByText('Chart — coming in Phase 2')).toBeVisible()
    await expect(page.getByText('Table — coming in Phase 2')).toBeVisible()
    await expect(page.getByText('Cost: -- (coming in Phase 2)')).toBeVisible()
  })
})
