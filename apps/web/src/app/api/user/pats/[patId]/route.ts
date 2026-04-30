import { NextResponse } from "next/server";

export async function DELETE() {
  return NextResponse.json(
    { detail: "PAT API is not supported in this deployment." },
    { status: 501 }
  );
}
