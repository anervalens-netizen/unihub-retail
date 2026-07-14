import { expect, test as base } from '@playwright/test';

export const test = base.extend({
  context: async ({ context }, use) => {
    const browserErrors: string[] = [];

    context.on('page', (page) => {
      page.on('pageerror', (error) => {
        browserErrors.push(`pageerror: ${error.message}`);
      });
      page.on('console', (message) => {
        if (message.type() === 'error') {
          browserErrors.push(`console.error: ${message.text()}`);
        }
      });
    });

    await use(context);

    expect(
      browserErrors,
      `Browser errors detected:\n${browserErrors.join('\n')}`,
    ).toEqual([]);
  },
});

export { expect };
