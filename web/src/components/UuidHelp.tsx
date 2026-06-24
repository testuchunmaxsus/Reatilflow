/**
 * UuidHelp — qayta ishlatiladigan UUID format yordam komponenti.
 *
 * Mantine Popover (click) + ActionIcon ichida IconInfoCircle.
 * Bosilganda UUID qanday yozilishi haqida xabar ko'rsatadi.
 *
 * Eslatma: ActionIcon "span" sifatida render qilinadi (renderRoot) —
 * bu label ichida ishlatilganda Testing Library getByLabelText testini
 * buzmasligi uchun (button labelable element, span emas).
 */

import { ActionIcon, Popover, Text } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface UuidHelpProps {
  /** Agar true bo'lsa xabarda "bo'sh qoldirsangiz ham bo'ladi" qo'shiladi */
  optional?: boolean;
}

export function UuidHelp({ optional }: UuidHelpProps) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);

  const message = optional
    ? t("common.uuid_help_optional", {
        defaultValue:
          "UUID — 36 belgilik identifikator (8-4-4-4-12 ko'rinishi), masalan: 0192f3a4-5b6c-7d8e-9f01-23456789abcd. Qiymatni ro'yxat yoki jadvaldan nusxa oling. Ixtiyoriy maydonni bo'sh qoldirsangiz ham bo'ladi.",
      })
    : t("common.uuid_help", {
        defaultValue:
          "UUID — 36 belgilik identifikator (8-4-4-4-12 ko'rinishi), masalan: 0192f3a4-5b6c-7d8e-9f01-23456789abcd. Qiymatni ro'yxat yoki jadvaldan nusxa oling. Majburiy maydon.",
      });

  return (
    <Popover
      width={300}
      position="top"
      withArrow
      shadow="md"
      opened={opened}
      onChange={setOpened}
    >
      <Popover.Target>
        <ActionIcon
          variant="subtle"
          size="xs"
          color="blue"
          aria-label="UUID format yordami"
          renderRoot={(props) => (
            // span sifatida render — label ichida labelable element bo'lmasin
            // type="button" span'ga taalluqli emas, shuning uchun olib tashlanadi
            <span
              {...props}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  setOpened((o) => !o);
                }
                if (typeof props.onKeyDown === "function") {
                  props.onKeyDown(e as React.KeyboardEvent<HTMLSpanElement>);
                }
              }}
              onClick={(e) => {
                e.stopPropagation();
                setOpened((o) => !o);
                if (typeof props.onClick === "function") {
                  props.onClick(e as React.MouseEvent<HTMLSpanElement>);
                }
              }}
            />
          )}
        >
          <IconInfoCircle size={15} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown>
        <Text size="xs">{message}</Text>
      </Popover.Dropdown>
    </Popover>
  );
}
