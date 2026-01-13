"use client";

type TokenGateProps = {
  children: React.ReactNode;
};

export default function TokenGate({ children }: TokenGateProps) {
  return (
    <>
      <div
        style={{
          margin: "1rem 0",
          padding: "0.75rem 1rem",
          border: "1px solid #cbd5f5",
          background: "#f8fbff",
          borderRadius: "6px",
          color: "#0f172a",
        }}
      >
        Demo access uses server-managed credentials. No token input required.
      </div>
      {children}
    </>
  );
}
