import { PageBody, PageHeader } from "@/components/record-page";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";

export function PendingPage({
  title,
  reason,
}: {
  title: string;
  reason: string;
}) {
  return (
    <PageBody>
      <PageHeader title={title} />
      <Empty>
        <EmptyHeader>
          <EmptyTitle>API support pending</EmptyTitle>
          <EmptyDescription>{reason}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </PageBody>
  );
}
