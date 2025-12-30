type Props = {
  title: string;
  children?: React.ReactNode;
};

export default function PanelServer({ title, children }: Props) {
  return (
    <section aria-label={title}>
      <header>
        <h2>{title}</h2>
      </header>
      <div>{children}</div>
    </section>
  );
}
