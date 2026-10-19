import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { TagInput } from "@/components/common";
import { StringListEditor } from "@/components/sortable";

function Controlled({ initial }: { initial: string[] }) {
  const [value, setValue] = React.useState(initial);
  return (
    <>
      <TagInput aria-label="Skills" value={value} onChange={setValue} />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  );
}

describe("TagInput", () => {
  it("adds on Enter and comma, skips duplicates, removes with the button and Backspace", async () => {
    const user = userEvent.setup();
    render(<Controlled initial={["SQL"]} />);
    const input = screen.getByLabelText("Skills");
    await user.type(input, "Python{Enter}sql{Enter}dbt,Spark,");
    expect(screen.getByTestId("value")).toHaveTextContent('["SQL","Python","dbt","Spark"]');
    await user.click(screen.getByRole("button", { name: "Remove Python" }));
    await user.type(input, "{Backspace}");
    expect(screen.getByTestId("value")).toHaveTextContent('["SQL","dbt"]');
  });
});

function Bullets() {
  const [value, setValue] = React.useState(["First"]);
  return (
    <>
      <StringListEditor value={value} onChange={setValue} itemLabel="Bullet" addLabel="Add bullet" />
      <output data-testid="bullets">{JSON.stringify(value)}</output>
    </>
  );
}

describe("StringListEditor", () => {
  it("adds, edits and removes bullets", async () => {
    const user = userEvent.setup();
    render(<Bullets />);
    await user.click(screen.getByRole("button", { name: "Add bullet" }));
    await user.type(screen.getByLabelText("Bullet 2"), "Second");
    expect(screen.getByTestId("bullets")).toHaveTextContent('["First","Second"]');
    await user.click(screen.getByRole("button", { name: "Remove bullet 1" }));
    expect(screen.getByTestId("bullets")).toHaveTextContent('["Second"]');
    expect(screen.getByRole("button", { name: /Reorder Bullet 1/ })).toBeInTheDocument();
  });
});
