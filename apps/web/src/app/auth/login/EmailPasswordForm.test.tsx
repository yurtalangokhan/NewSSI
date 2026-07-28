/**
 * Integration Test: Email/Password Authentication Workflow
 *
 * Tests the complete user journey for logging in.
 * This tests the full workflow: form → validation → API call → redirect
 */
import React from "react";
import { render, screen, waitFor, setupUser } from "@tests/setup/test-utils";
import EmailPasswordForm from "./EmailPasswordForm";

// Mock next/navigation (not used by this component, but required by dependencies)
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    refresh: jest.fn(),
  }),
}));

describe("Email/Password Login Workflow", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    fetchSpy = jest.spyOn(global, "fetch");
    // Mock window.location.href for redirect testing
    delete (window as any).location;
    window.location = { href: "" } as any;
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  test("allows user to login with valid credentials", async () => {
    const user = setupUser();

    // Mock POST /api/auth/login
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<EmailPasswordForm isSignup={false} />);

    // User fills out the form using placeholder text
    const emailInput = screen.getByTestId("username");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "password123");

    // User submits the form
    const loginButton = screen.getByRole("button", {
      name: /auth\.signInButton/i,
    });
    await user.click(loginButton);

    // After successful login, user should be redirected to /chat
    await waitFor(() => {
      expect(window.location.href).toBe("/app");
    });

    // Verify API was called with correct credentials
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      })
    );

    // Verify the request body contains the username. The password is also sent
    // by browser password-login flows, but tests should not normalize printing it.
    const callArgs = fetchSpy.mock.calls[0];
    const body = callArgs[1].body;
    expect(body.toString()).toContain("username=test%40example.com");
  });

  test("uses the external Keycloak login endpoint for external provider login", async () => {
    const user = setupUser();

    // Mock POST /api/auth/external/login
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    await user.type(screen.getByTestId("username"), "external@example.com");
    await user.type(screen.getByPlaceholderText(/∗/), "password123");
    await user.click(
      screen.getByRole("button", {
        name: /auth\.signInButton/i,
      })
    );

    await waitFor(() => {
      expect(window.location.href).toBe("/app");
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/external/login",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      })
    );
  });

  test("shows proxy error details instead of unknown error", async () => {
    const user = setupUser();

    // Mock POST /api/auth/external/login through the Next.js proxy
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ error: "Backend service unavailable" }),
      text: async () => JSON.stringify({ error: "Backend service unavailable" }),
    } as unknown as Response);

    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    await user.type(screen.getByTestId("username"), "external@example.com");
    await user.type(screen.getByPlaceholderText(/∗/), "password123");
    await user.click(
      screen.getByRole("button", {
        name: /auth\.signInButton/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("Backend service unavailable")).toBeInTheDocument();
    });
  });

  test("shows error message when login fails", async () => {
    const user = setupUser();

    // Mock POST /api/auth/login (failure)
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "LOGIN_BAD_CREDENTIALS" }),
    } as Response);

    render(<EmailPasswordForm isSignup={false} />);

    // User fills out form with invalid credentials
    const emailInput = screen.getByTestId("username");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(emailInput, "wrong@example.com");
    await user.type(passwordInput, "wrongpassword");

    // User submits
    const loginButton = screen.getByRole("button", {
      name: /auth\.signInButton/i,
    });
    await user.click(loginButton);

    // Verify field-level error message is displayed (not the toast)
    await waitFor(() => {
      expect(
        screen.getByText(/^auth\.invalidCredentials$/i)
      ).toBeInTheDocument();
    });
  });
});

describe("Email/Password Signup Workflow", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    fetchSpy = jest.spyOn(global, "fetch");
    // Mock window.location.href
    delete (window as any).location;
    window.location = { href: "" } as any;
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  test("allows user to sign up and redirect with valid credentials", async () => {
    const user = setupUser();

    // Mock POST /api/auth/register
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<EmailPasswordForm isSignup={true} />);

    // User fills out the signup form
    const usernameInput = screen.getByTestId("username");
    const emailInput = screen.getByTestId("email");
    const firstNameInput = screen.getByTestId("firstName");
    const lastNameInput = screen.getByTestId("lastName");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(usernameInput, "newuser");
    await user.type(emailInput, "newuser@example.com");
    await user.type(firstNameInput, "John");
    await user.type(lastNameInput, "Doe");
    await user.type(passwordInput, "securepassword123");

    // User submits the signup form
    const signupButton = screen.getByRole("button", {
      name: /auth\.createAccountButton/i,
    });
    await user.click(signupButton);

    // Verify signup API was called
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/auth/register",
        expect.objectContaining({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        })
      );
    });

    // Verify signup request body
    const signupCallArgs = fetchSpy.mock.calls[0];
    const signupBody = JSON.parse(signupCallArgs[1].body);
    expect(signupBody).toEqual({
      email: "newuser@example.com",
      username: "newuser",
      password: "securepassword123",
      first_name: "John",
      last_name: "Doe",
    });

    await waitFor(() => {
      expect(window.location.href).toBe("/app?new_team=true");
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("shows error when email already exists", async () => {
    const user = setupUser();

    // Mock POST /api/auth/register (failure - user exists)
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: "REGISTER_USER_ALREADY_EXISTS" }),
    } as Response);

    render(<EmailPasswordForm isSignup={true} />);

    // User fills out form with existing email
    const usernameInput = screen.getByTestId("username");
    const emailInput = screen.getByTestId("email");
    const firstNameInput = screen.getByTestId("firstName");
    const lastNameInput = screen.getByTestId("lastName");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(usernameInput, "existinguser");
    await user.type(emailInput, "existing@example.com");
    await user.type(firstNameInput, "Jane");
    await user.type(lastNameInput, "Doe");
    await user.type(passwordInput, "password123");

    // User submits
    const signupButton = screen.getByRole("button", {
      name: /auth\.createAccountButton/i,
    });
    await user.click(signupButton);

    // Verify field-level error message is displayed (not the toast)
    await waitFor(() => {
      expect(
        screen.getByText(/^auth\.accountAlreadyExists$/i)
      ).toBeInTheDocument();
    });
  });

  test("shows rate limit error when too many requests", async () => {
    const user = setupUser();

    // Mock POST /api/auth/register (failure - rate limit)
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 429,
      json: async () => ({ detail: "Too many requests" }),
    } as Response);

    render(<EmailPasswordForm isSignup={true} />);

    // User fills out form
    const usernameInput = screen.getByTestId("username");
    const emailInput = screen.getByTestId("email");
    const firstNameInput = screen.getByTestId("firstName");
    const lastNameInput = screen.getByTestId("lastName");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(usernameInput, "rateuser");
    await user.type(emailInput, "user@example.com");
    await user.type(firstNameInput, "Rate");
    await user.type(lastNameInput, "Limited");
    await user.type(passwordInput, "password123");

    // User submits
    const signupButton = screen.getByRole("button", {
      name: /auth\.createAccountButton/i,
    });
    await user.click(signupButton);

    // Verify field-level rate limit message is displayed (not the toast)
    await waitFor(() => {
      expect(screen.getByText(/^auth\.tooManyRequests$/i)).toBeInTheDocument();
    });
  });
});
