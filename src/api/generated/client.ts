import { client } from '../client';
import {
  RETAIL_OPERATION_ROUTES,
  type RetailOperationId,
  type RetailOperationResponses,
} from './contracts';
import { decodeRetail, type DecodeRetail } from './decoded';

type SuccessResponse<Id extends RetailOperationId> =
  RetailOperationResponses[Id] extends { '200': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '201': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '202': infer Response } ? Response :
  RetailOperationResponses[Id] extends { '204': infer Response } ? Response :
  never;

export type GeneratedRequestOptions = {
  params?: object;
  pathParams?: Record<string, string | number>;
  responseType?: 'blob' | 'json';
  signal?: AbortSignal;
};

function resolvePath(path: string, pathParams?: Record<string, string | number>): string {
  return path.replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = pathParams?.[key];
    if (value === undefined) throw new Error(`Missing path parameter ${key}`);
    return encodeURIComponent(String(value));
  });
}

export async function generatedGet<Id extends RetailOperationId>(
  operationId: Id,
  options?: GeneratedRequestOptions,
): Promise<DecodeRetail<SuccessResponse<Id>>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== 'get') {
    throw new Error(`Operation ${operationId} is not a GET route`);
  }
  const { data } = await client.get<SuccessResponse<Id>>(resolvePath(route.path, options?.pathParams), options);
  return decodeRetail<SuccessResponse<Id>>(data);
}

export async function generatedPost<Id extends RetailOperationId>(
  operationId: Id,
  body: unknown,
  options?: GeneratedRequestOptions,
): Promise<DecodeRetail<SuccessResponse<Id>>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== 'post') {
    throw new Error(`Operation ${operationId} is not a POST route`);
  }
  const { data } = await client.post<SuccessResponse<Id>>(
    resolvePath(route.path, options?.pathParams),
    body,
    options,
  );
  return decodeRetail<SuccessResponse<Id>>(data);
}

export async function generatedPatch<Id extends RetailOperationId>(
  operationId: Id,
  body: unknown,
  options?: GeneratedRequestOptions,
): Promise<DecodeRetail<SuccessResponse<Id>>> {
  const route = RETAIL_OPERATION_ROUTES[operationId];
  if (route.method !== 'patch') {
    throw new Error(`Operation ${operationId} is not a PATCH route`);
  }
  const { data } = await client.patch<SuccessResponse<Id>>(
    resolvePath(route.path, options?.pathParams),
    body,
    options,
  );
  return decodeRetail<SuccessResponse<Id>>(data);
}
