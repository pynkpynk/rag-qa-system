"use client";

import { useState } from "react";

type Props = {
  initialCount?: number;
};

export default function CounterClient({ initialCount = 0 }: Props) {
  const [count, setCount] = useState(initialCount);

  return (
    <div>
      <p>Count: {count}</p>
      <button type="button" onClick={() => setCount((c) => c + 1)}>
        +1
      </button>
    </div>
  );
}
