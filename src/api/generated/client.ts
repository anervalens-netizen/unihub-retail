/* HANDWRITTEN RETAIL BOUNDARY: BFF transport over generated contracts. */
import { ApiError, client } from "../client";
import {
  RETAIL_OPERATION_ERROR_STATUSES,
  RETAIL_OPERATION_ROUTES,
  type RetailOperationBodies,
  type RetailOperationErrors,
  type RetailOperationId,
  type RetailOperationPaths,
  type RetailOperationQueries,
  type RetailOperationSuccesses,
} from "./contracts";
import { decodeRetail, type DecodeRetail } from "./decoded";
import type { RequiredRuntime } from "./runtime-types";

type SuccessResponse<Id extends RetailOperationId> =
  RetailOperationSuccesses[Id];

type MethodOperation<Method extends string> = {
  [
    Id in RetailOperationId
  ]: (typeof RETAIL_OPERATION_ROUTES)[Id]["method"] extends Method ? Id : never;
}[RetailOperationId];

type RequiredKeys<Value> = {
  [Key in keyof Value]-?: Pick<Value, Key> extends Required<Pick<Value, Key>>
    ? Key
    : never;
}[keyof Value];

type HasKeys<Value> = keyof Value extends never ? false : true;
type HasRequiredKeys<Value> = [RequiredKeys<Value>] extends [never]
  ? false
  : true;

export type GeneratedRequestOptions<Id extends RetailOperationId> = (HasKeys<
  RetailOperationQueries[Id]
> extends true
  ? HasRequiredKeys<RetailOperationQueries[Id]> extends true
    ? { params: RetailOperationQueries[Id] }
    : { params?: RetailOperationQueries[Id] }
  : { params?: never }) &
  (HasKeys<RetailOperationPaths[Id]> extends true
    ? HasRequiredKeys<RetailOperationPaths[Id]> extends true
      ? { pathParams: RetailOperationPaths[Id] }
      : { pathParams?: RetailOperationPaths[Id] }
    : { pathParams?: never }) & {
    signal?: AbortSignal;
  };

type OptionsArgs<Id extends RetailOperationId> =
  HasRequiredKeys<RetailOperationQueries[Id]> extends true
    ? [options: GeneratedRequestOptions<Id>]
    : HasRequiredKeys<RetailOperationPaths[Id]> extends true
      ? [options: GeneratedRequestOptions<Id>]
      : [options?: GeneratedRequestOptions<Id>];

type Result<Id extends RetailOperationId> = RequiredRuntime<
  DecodeRetail<SuccessResponse<Id>>
>;
type RequestBody<Id extends RetailOperationId> = DecodeRetail<
  RetailOperationBodies[Id]
>;
type OperationErrorStatus<Id extends RetailOperationId> =
  keyof RetailOperationErrors[Id] & string;
type OperationErrorBody<Id extends RetailOperationId> =
  RetailOperationErrors[Id][OperationErrorStatus<Id>];

/**
 * BFF-compatible ApiError carrying the generated operation identity and its
 * documented error-body union. It remains an ApiError for existing callers.
 */
export class GeneratedApiError<Id extends RetailOperationId> extends ApiError {
  readonly operationId: Id;
  readonly expected: boolean;
  readonly typedBody: OperationErrorBody<Id> | undefined;

  constructor(operationId: Id, error: ApiError) {
    super(error.status, error.detail, error.body);
    this.name = "GeneratedApiError";
    this.operationId = operationId;
    this.expected = RETAIL_OPERATION_ERROR_STATUSES[operationId].has(
      String(error.status),
    );
    this.typedBody = this.expected
      ? (error.body as OperationErrorBody<Id>)
      : undefined;
  }
}

export function isGeneratedApiError<Id extends RetailOperationId>(
  error: unknown,
  operationId: Id,
): error is GeneratedApiError<Id> {
  return (
    error instanceof GeneratedApiError && error.operationId === operationId
  );
}

function resolvePath<Id extends RetailOperationId>(
  path: string,
  pathParams?: RetailOperationPaths[Id],
): string {
  return path.replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = pathParams?.[key as keyof RetailOperationPaths[Id]];
    if (value === undefined) throw new Error(`Missing path parameter ${key}`);
    return encodeURIComponent(String(value));
  });
}

async function request<Id extends RetailOperationId>(
  operationId: Id,
  method: "get" | "post" | "patch",
  body: RequestBody<Id> | undefined,
  options?: GeneratedRequestOptions<Id>,
): Promise<Result<Id>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== method)
    throw new Error(
      `Operation ${operationId} is not a ${method.toUpperCase()} route`,
    );
  const path = resolvePath<Id>(route.path, options?.pathParams);
  const requestOptions = {
    params: options?.params,
    signal: options?.signal,
    responseType: route.responseType,
  } as const;
  try {
    const response =
      method === "get"
        ? await client.get<SuccessResponse<Id>>(path, requestOptions)
        : method === "post"
          ? await client.post<SuccessResponse<Id>>(path, body, requestOptions)
          : await client.patch<SuccessResponse<Id>>(path, body, requestOptions);
    return decodeRetail(operationId, response.data) as Result<Id>;
  } catch (error) {
    if (error instanceof ApiError)
      throw new GeneratedApiError(operationId, error);
    throw error;
  }
}

export function generatedGet<Id extends MethodOperation<"get">>(
  operationId: Id,
  ...[options]: OptionsArgs<NoInfer<Id>>
): Promise<Result<Id>> {
  return request(operationId, "get", undefined, options);
}

export function generatedPost<Id extends MethodOperation<"post">>(
  operationId: Id,
  body: RequestBody<NoInfer<Id>>,
  ...[options]: OptionsArgs<NoInfer<Id>>
): Promise<Result<Id>> {
  return request(operationId, "post", body, options);
}

export function generatedPatch<Id extends MethodOperation<"patch">>(
  operationId: Id,
  body: RequestBody<NoInfer<Id>>,
  ...[options]: OptionsArgs<NoInfer<Id>>
): Promise<Result<Id>> {
  return request(operationId, "patch", body, options);
}
