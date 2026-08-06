/**
 * Compatibility exports for feature modules.
 *
 * The source of truth is the generated OpenAPI contract plus its runtime
 * Decimal decoder in generated/runtime-types.ts. Keep this module only while
 * feature imports are migrated; it must not contain hand-maintained schemas.
 */
export * from './generated/runtime-types';
