import { useState, type FormEvent } from "react";
import { CalendarCheck, Search } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";

type CalendarTestAvailability =
  components["schemas"]["CalendarTestAvailabilityResponse"];
type CalendarTestBooking = components["schemas"]["CalendarTestBookingResponse"];

type CalendarIntegrationTestDialogProps = {
  integrationId: string;
  integrationName: string;
  disabled: boolean;
};

export function CalendarIntegrationTestDialog({
  integrationId,
  integrationName,
  disabled,
}: CalendarIntegrationTestDialogProps) {
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [availability, setAvailability] =
    useState<CalendarTestAvailability | null>(null);
  const [selectedSlotId, setSelectedSlotId] = useState("");
  const [summary, setSummary] = useState("Voice AI calendar integration test");
  const [description, setDescription] = useState(
    "Test event created from the Voice AI integrations dashboard.",
  );
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [booking, setBooking] = useState(false);
  const [confirmation, setConfirmation] = useState<CalendarTestBooking | null>(
    null,
  );

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setAvailability(null);
      setSelectedSlotId("");
      setConfirmation(null);
    }
  }

  async function loadAvailability() {
    setLoadingSlots(true);
    setConfirmation(null);
    try {
      const result = await api<CalendarTestAvailability>(
        `/calendar-integrations/${integrationId}/test/availability`,
        {
          method: "POST",
          body: JSON.stringify({ limit: 5 }),
        },
      );
      setAvailability(result);
      setSelectedSlotId(result.slots[0]?.slot_id ?? "");
      if (result.slots.length === 0) {
        toast.warning(
          "No free 15-minute slots were found in the next seven days.",
        );
      } else {
        toast.success(`Found ${result.slots.length} free calendar slots.`);
      }
    } catch (cause) {
      setAvailability(null);
      setSelectedSlotId("");
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not check Google Calendar availability",
      );
    } finally {
      setLoadingSlots(false);
    }
  }

  async function bookTestEvent(event: FormEvent) {
    event.preventDefault();
    if (!selectedSlotId) return;
    setBooking(true);
    setConfirmation(null);
    try {
      const result = await api<CalendarTestBooking>(
        `/calendar-integrations/${integrationId}/test/book`,
        {
          method: "POST",
          body: JSON.stringify({
            slot_id: selectedSlotId,
            summary: summary.trim(),
            description: description.trim(),
          }),
        },
      );
      setConfirmation(result);
      setAvailability(null);
      setSelectedSlotId("");
      toast.success("The 15-minute test event was added to Google Calendar.");
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not create the Google Calendar test event",
      );
    } finally {
      setBooking(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled}>
          <CalendarCheck data-icon="inline-start" />
          Test calendar
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={bookTestEvent} className="flex flex-col gap-6">
          <DialogHeader>
            <DialogTitle>Test {integrationName}</DialogTitle>
            <DialogDescription>
              Check Google free/busy data, then create one real 15-minute test
              event. This does not create a callback or start a call.
            </DialogDescription>
          </DialogHeader>

          <FieldGroup>
            {availability ? (
              <Field>
                <FieldLabel htmlFor={`calendar-slot-${integrationId}`}>
                  Available 15-minute slot
                </FieldLabel>
                <NativeSelect
                  id={`calendar-slot-${integrationId}`}
                  className="w-full"
                  value={selectedSlotId}
                  onChange={(event) => setSelectedSlotId(event.target.value)}
                  required
                >
                  {availability.slots.length === 0 ? (
                    <NativeSelectOption value="">
                      No free slots found
                    </NativeSelectOption>
                  ) : (
                    availability.slots.map((slot) => (
                      <NativeSelectOption
                        key={slot.slot_id}
                        value={slot.slot_id}
                      >
                        {slot.display}
                      </NativeSelectOption>
                    ))
                  )}
                </NativeSelect>
                <FieldDescription>
                  Times use the calendar timezone: {availability.timezone}.
                  Slots expire after five minutes and are rechecked before
                  booking.
                </FieldDescription>
              </Field>
            ) : null}

            <Field>
              <FieldLabel htmlFor={`calendar-summary-${integrationId}`}>
                Event title
              </FieldLabel>
              <Input
                id={`calendar-summary-${integrationId}`}
                value={summary}
                maxLength={200}
                onChange={(event) => setSummary(event.target.value)}
                required
              />
            </Field>

            <Field>
              <FieldLabel htmlFor={`calendar-description-${integrationId}`}>
                Event description
              </FieldLabel>
              <Textarea
                id={`calendar-description-${integrationId}`}
                value={description}
                maxLength={2000}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </FieldGroup>

          {confirmation ? (
            <Alert>
              <CalendarCheck />
              <AlertTitle>Test event created</AlertTitle>
              <AlertDescription>
                {confirmation.scheduled_time} for{" "}
                {confirmation.duration_minutes}
                minutes.
              </AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={loadingSlots || booking}
              onClick={() => void loadAvailability()}
            >
              {loadingSlots ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <Search data-icon="inline-start" />
              )}
              Find 5 free slots
            </Button>
            <Button
              type="submit"
              disabled={
                booking || loadingSlots || !selectedSlotId || !summary.trim()
              }
            >
              {booking ? <Spinner data-icon="inline-start" /> : null}
              Book selected slot
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
