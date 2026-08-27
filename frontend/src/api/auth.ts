import request from "@/api/request";
import type { LoginRequest, AuthResult, RegisterRequest } from "@/types/auth";

export function login(req: LoginRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/login", req);
}

export function register(req: RegisterRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/register", req);
}
