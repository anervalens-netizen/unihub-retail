import { describe, expect, it, vi } from 'vitest';

import { ApiError } from './client';
import { GeneratedApiError, generatedPost } from './generated/client';
import { createSalaryExportOperation, uncertainSalaryExportOperationId } from './salarii';

vi.mock('./generated/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./generated/client')>();
  return { ...actual, generatedPost: vi.fn() };
});

const operationId = 'create_salary_export_operation_salarii_exports_operations_post' as const;

describe('uncertainSalaryExportOperationId', () => {
  it('retains the server-reserved id after an uncertain queue publish', () => {
    const error = new GeneratedApiError(
      operationId,
      new ApiError(503, 'temporar indisponibil', {
        detail: { operation_id: 42, status: 'unknown' },
      }),
    );

    expect(uncertainSalaryExportOperationId(error)).toBe(42);
  });

  it('rejects non-503 and malformed details', () => {
    expect(
      uncertainSalaryExportOperationId(
        new GeneratedApiError(
          operationId,
          new ApiError(409, 'conflict', { detail: { operation_id: 42 } }),
        ),
      ),
    ).toBeNull();
    expect(
      uncertainSalaryExportOperationId(
        new GeneratedApiError(
          operationId,
          new ApiError(503, 'temporar indisponibil', { detail: 'retry' }),
        ),
      ),
    ).toBeNull();
  });
});

describe('createSalaryExportOperation', () => {
  it('uses the generated server-owned salary export operation', async () => {
    const operation = { id: 7, status: 'queued' };
    vi.mocked(generatedPost).mockResolvedValueOnce(operation as never);

    await expect(createSalaryExportOperation({ export_kind: 'monthly_trend' }))
      .resolves.toBe(operation);
    expect(generatedPost).toHaveBeenCalledWith(
      'create_salary_export_operation_salarii_exports_operations_post',
      { export_kind: 'monthly_trend' },
    );
  });
});
