/**
 * Integration Test: Email/Password Authentication Workflow
 *
 * Tests the complete user journey for logging in.
 * This tests the full workflow: form → validation → API call → redirect
 */
import { fakeResponse } from "@tests/setup/responseModel";
import React from "react";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
  setupUser,
} from "@tests/setup/test-utils";
import EmailPasswordForm from "./EmailPasswordForm";

const signInButtonText = /^(auth\.signInButton|Sign In)$/i;
const createAccountButtonText = /^(auth\.createAccountButton|Create Account)$/i;
const invalidCredentialsText =
  /^(auth\.invalidCredentials|Invalid username\/email or password)$/i;
const accountAlreadyExistsText =
  /^(auth\.accountAlreadyExists|An account already exists with the specified email\.)$/i;
const tooManyRequestsText =
  /^(auth\.tooManyRequests|Too many requests\. Please try again later\.)$/i;

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
    fetchSpy.mockResolvedValueOnce(fakeResponse(true, undefined, {}));

    render(<EmailPasswordForm isSignup={false} />);

    // User fills out the form using placeholder text
    const emailInput = screen.getByTestId("username");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "password123");

    // User submits the form
    const loginButton = screen.getByRole("button", {
      name: signInButtonText,
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
      })
    );
    expect(
      new Headers(fetchSpy.mock.calls[0]?.[1]?.headers).get("Content-Type")
    ).toBe("application/x-www-form-urlencoded");

    // Verify the request body contains the username. The password is also sent
    // by browser password-login flows, but tests should not normalize printing it.
    const callArgs = fetchSpy.mock.calls[0];
    const body = callArgs[1].body;
    expect(body.toString()).toContain("username=test%40example.com");
  });

  test("uses the external Keycloak login endpoint for external provider login", async () => {
    const user = setupUser();

    // Mock POST /api/auth/external/login
    fetchSpy.mockResolvedValueOnce(
      fakeResponse(true, undefined, {
        authorization_url: "http://keycloak/realms/agenticai/auth",
      })
    );

    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    await user.type(screen.getByTestId("username"), "external@example.com");
    await user.type(screen.getByPlaceholderText(/∗/), "password123");
    await user.click(
      screen.getByRole("button", {
        name: signInButtonText,
      })
    );

    await waitFor(() => {
      expect(window.location.href).toBe(
        "http://keycloak/realms/agenticai/auth"
      );
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/external/login",
      expect.objectContaining({
        method: "POST",
      })
    );
    expect(
      new Headers(fetchSpy.mock.calls[0]?.[1]?.headers).get("Content-Type")
    ).toBe("application/x-www-form-urlencoded");
  });

  test("shows proxy error details instead of unknown error", async () => {
    const user = setupUser();

    // Mock POST /api/auth/external/login through the Next.js proxy
    fetchSpy.mockResolvedValueOnce(
      fakeResponse(false, 503, {
        message: "Backend service unavailable",
      })
    );

    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    await user.type(screen.getByTestId("username"), "external@example.com");
    await user.type(screen.getByPlaceholderText(/∗/), "password123");
    await user.click(
      screen.getByRole("button", {
        name: signInButtonText,
      })
    );

    await waitFor(() => {
      expect(
        screen.getByText("Backend service unavailable")
      ).toBeInTheDocument();
    });
  });

  test("shows the unavailable message when the gateway answers with its HTML 502 page", async () => {
    const user = setupUser();

    // Mock POST /api/auth/login: the gateway could not reach user-service and
    // answered with nginx's page instead of the error envelope.
    fetchSpy.mockResolvedValueOnce(
      new Response(
        "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n" +
          "<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>openresty</center>\r\n" +
          "</body>\r\n</html>\r\n",
        { status: 502, headers: { "Content-Type": "text/html" } }
      )
    );

    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    await user.type(screen.getByTestId("username"), "external@example.com");
    await user.type(screen.getByPlaceholderText(/∗/), "password123");
    await user.click(
      screen.getByRole("button", {
        name: signInButtonText,
      })
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "The service is currently unavailable. Please try again."
        )
      ).toBeInTheDocument();
    });
    // The markup of the gateway page never reaches the user.
    expect(screen.queryByText(/502 Bad Gateway/)).not.toBeInTheDocument();
    expect(screen.queryByText(/<html>/)).not.toBeInTheDocument();
  });

  test("shows error message when login fails", async () => {
    const user = setupUser();

    // Mock POST /api/auth/login (failure)
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          statusCode: 401,
          message: "Invalid username or password",
          data: null,
          error: {
            code: "auth.invalid_credentials",
            message: "Invalid username or password",
          },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      )
    );

    render(<EmailPasswordForm isSignup={false} />);

    // User fills out form with invalid credentials
    const emailInput = screen.getByTestId("username");
    const passwordInput = screen.getByPlaceholderText(/∗/);

    await user.type(emailInput, "wrong@example.com");
    await user.type(passwordInput, "wrongpassword");

    // User submits
    const loginButton = screen.getByRole("button", {
      name: signInButtonText,
    });
    await user.click(loginButton);

    // Verify field-level error message is displayed (not the toast)
    await waitFor(() => {
      expect(screen.getByText(invalidCredentialsText)).toBeInTheDocument();
    });
  });

  test("displays caps lock warning when typing password with Caps Lock on and hides on blur", async () => {
    render(<EmailPasswordForm isSignup={false} loginProvider="external" />);

    const passwordInput = screen.getByPlaceholderText(/∗/);

    // Warning is not visible initially
    expect(screen.queryByTestId("caps-lock-warning")).not.toBeInTheDocument();

    // Trigger keydown with modifierCapsLock = true
    act(() => {
      fireEvent.keyDown(passwordInput, { key: "a", modifierCapsLock: true });
    });

    await waitFor(() => {
      expect(screen.getByTestId("caps-lock-warning")).toBeInTheDocument();
    });

    // When Caps Lock is turned off
    act(() => {
      fireEvent.keyDown(passwordInput, { key: "a", modifierCapsLock: false });
    });

    await waitFor(() => {
      expect(screen.queryByTestId("caps-lock-warning")).not.toBeInTheDocument();
    });

    // Turning it on again and then blurring
    act(() => {
      fireEvent.keyDown(passwordInput, { key: "a", modifierCapsLock: true });
    });
    expect(screen.getByTestId("caps-lock-warning")).toBeInTheDocument();

    act(() => {
      fireEvent.blur(passwordInput);
    });
    expect(screen.queryByTestId("caps-lock-warning")).not.toBeInTheDocument();
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
    fetchSpy.mockResolvedValueOnce(fakeResponse(true, undefined, {}));

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
      name: createAccountButtonText,
    });
    await user.click(signupButton);

    // Verify signup API was called
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/auth/register",
        expect.objectContaining({
          method: "POST",
        })
      );
    });

    // Verify signup request body
    const signupCallArgs = fetchSpy.mock.calls[0];
    const signupInit = signupCallArgs[1] as RequestInit;
    const signupHeaders = new Headers(signupInit.headers);
    expect(signupHeaders.get("Content-Type")).toBe("application/json");
    expect(signupHeaders.has("Idempotency-Key")).toBe(true);
    const signupBody = JSON.parse(signupInit.body as string);
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
    fetchSpy.mockResolvedValueOnce(
      fakeResponse(false, 400, { detail: "REGISTER_USER_ALREADY_EXISTS" })
    );

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
      name: createAccountButtonText,
    });
    await user.click(signupButton);

    // Verify field-level error message is displayed (not the toast)
    await waitFor(() => {
      expect(screen.getByText(accountAlreadyExistsText)).toBeInTheDocument();
    });
  });

  test("shows rate limit error when too many requests", async () => {
    const user = setupUser();

    // Mock POST /api/auth/register (failure - rate limit)
    fetchSpy.mockResolvedValueOnce(
      fakeResponse(false, 429, { detail: "Too many requests" })
    );

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
      name: createAccountButtonText,
    });
    await user.click(signupButton);

    // Verify field-level rate limit message is displayed (not the toast)
    await waitFor(() => {
      expect(screen.getByText(tooManyRequestsText)).toBeInTheDocument();
    });
  });
});
