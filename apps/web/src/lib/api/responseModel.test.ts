import { parseResponseModel } from "@/lib/api/responseModel";

function envelope(statusCode: number, message = "İstek reddedildi.") {
  return {
    statusCode,
    message,
    data: null,
    error: { code: "auth.forbidden", message },
  };
}

it.each([200, 422, 500])(
  "rejects error HTTP/body status mismatch %s",
  async (bodyStatus) => {
    const response = Response.json(envelope(bodyStatus), { status: 403 });
    await expect(parseResponseModel(response)).rejects.toMatchObject({
      status: 502,
      code: "dependency.invalid_response",
    });
  }
);

it("keeps matching error code and localized message", async () => {
  await expect(
    parseResponseModel(Response.json(envelope(403), { status: 403 }))
  ).rejects.toMatchObject({
    status: 403,
    code: "auth.forbidden",
    message: "İstek reddedildi.",
  });
});

it("continues parsing legacy non-envelope errors", async () => {
  await expect(
    parseResponseModel(
      Response.json({ detail: "Invalid value." }, { status: 422 })
    )
  ).rejects.toMatchObject({
    status: 422,
    message: "Invalid value.",
  });
});
