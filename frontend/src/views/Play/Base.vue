<script setup lang="ts">
import type { FirmwareSchema, SaveSchema, StateSchema } from "@/__generated__";
import RAvatar from "@/components/common/Game/RAvatar.vue";
import firmwareApi from "@/services/api/firmware";
import romApi from "@/services/api/rom";
import type { DetailedRom } from "@/stores/roms";
import { formatBytes, formatTimestamp, getSupportedCores } from "@/utils";
import Player from "@/views/Play/Player.vue";
import { isNull } from "lodash";
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

// Props
const route = useRoute();
const rom = ref<DetailedRom | null>(null);
const firmwareOptions = ref<FirmwareSchema[]>([]);
const biosRef = ref<FirmwareSchema | null>(null);
const saveRef = ref<SaveSchema | null>(null);
const stateRef = ref<StateSchema | null>(null);
const supportedCores = ref<string[]>([]);
const coreRef = ref<string | null>(null);
const gameRunning = ref(false);
const storedFSOP = localStorage.getItem("fullScreenOnPlay");
const fullScreenOnPlay = ref(isNull(storedFSOP) ? true : storedFSOP === "true");
const script = document.createElement("script");
script.src = "/assets/emulatorjs/loader.js";
script.async = true;

// Functions
function onPlay() {
  window.EJS_fullscreenOnLoaded = fullScreenOnPlay.value;
  document.body.appendChild(script);
  gameRunning.value = true;
}

function onFullScreenChange() {
  fullScreenOnPlay.value = !fullScreenOnPlay.value;
  localStorage.setItem("fullScreenOnPlay", fullScreenOnPlay.value.toString());
}

onMounted(async () => {
  const romResponse = await romApi.getRom({
    romId: parseInt(route.params.rom as string),
  });
  rom.value = romResponse.data;
  supportedCores.value = [...getSupportedCores(rom.value.platform_slug)];
  coreRef.value = supportedCores.value[0];

  const firmwareResponse = await firmwareApi.getFirmware({
    platformId: romResponse.data.platform_id,
  });
  firmwareOptions.value = firmwareResponse.data;
  // Auto select most recent state
  if (rom.value.user_states && rom.value.user_states?.length > 0) {
    stateRef.value = rom.value.user_states.sort((a, b) =>
      b.updated_at.localeCompare(a.updated_at)
    )[0];
  }
});
</script>

<template>
  <v-row v-if="rom" class="align-center justify-center scroll" no-gutters>
    <v-col
      v-if="gameRunning"
      cols="12"
      md="8"
      xl="10"
      id="game-wrapper"
      class="bg-primary"
      rounded
    >
      <player
        :rom="rom"
        :state="stateRef"
        :save="saveRef"
        :bios="biosRef"
        :core="coreRef"
      />
    </v-col>

    <v-col
      cols="12"
      :sm="!gameRunning ? 10 : 10"
      :md="!gameRunning ? 8 : 4"
      :xl="!gameRunning ? 6 : 2"
    >
      <v-row class="px-3 mt-6" no-gutters>
        <v-col>
          <v-img
            class="mx-auto"
            width="250"
            src="/assets/emulatorjs/powered_by_emulatorjs.png"
          />
          <v-divider class="my-4" />
          <v-list-item class="px-2">
            <template #prepend>
              <r-avatar :rom="rom" />
            </template>
            <v-row no-gutters
              ><v-col>{{ rom.name }}</v-col></v-row
            >
            <v-row no-gutters
              ><v-col class="text-romm-accent-1">{{
                rom.file_name
              }}</v-col></v-row
            >
          </v-list-item>
          <v-divider class="my-4" />
          <v-select
            v-if="supportedCores.length > 1"
            :disabled="gameRunning"
            v-model="coreRef"
            class="my-1"
            rounded="0"
            hide-details
            variant="outlined"
            clearable
            label="Core"
            :items="
              supportedCores.map((c) => ({
                title: c,
                value: c,
              }))
            "
          />
          <v-select
            v-model="biosRef"
            :disabled="gameRunning"
            class="my-1"
            hide-details
            rounded="0"
            variant="outlined"
            clearable
            label="BIOS"
            :items="
              firmwareOptions.map((f) => ({
                title: f.file_name,
                value: f,
              })) ?? []
            "
          />
          <v-select
            v-model="saveRef"
            :disabled="gameRunning"
            class="my-1"
            hide-details
            variant="outlined"
            clearable
            rounded="0"
            label="Save"
            :items="
              rom.user_saves?.map((s) => ({
                title: s.file_name,
                subtitle: `${s.emulator} - ${formatBytes(s.file_size_bytes)}`,
                value: s,
              })) ?? []
            "
          >
            <template #selection="{ item }">
              <v-list-item class="py-4" :title="item.value.file_name ?? ''">
                <template #append>
                  <v-chip size="x-small" class="ml-1" color="orange" label>{{
                    item.value.emulator
                  }}</v-chip>
                  <v-chip size="x-small" class="ml-1" label>
                    {{ formatTimestamp(item.value.updated_at) }}
                  </v-chip>
                  <v-chip size="x-small" class="ml-1" label
                    >{{ formatBytes(item.value.file_size_bytes) }}
                  </v-chip>
                </template>
              </v-list-item>
            </template>
            <template #item="{ props, item }">
              <v-list-item
                class="py-4"
                v-bind="props"
                :title="item.value.file_name ?? ''"
              >
                <template #append>
                  <v-chip size="x-small" class="ml-1" color="orange" label>{{
                    item.value.emulator
                  }}</v-chip>
                  <v-chip size="x-small" class="ml-1" label>
                    {{ formatTimestamp(item.value.updated_at) }}
                  </v-chip>
                  <v-chip size="x-small" class="ml-1" label
                    >{{ formatBytes(item.value.file_size_bytes) }}
                  </v-chip>
                </template>
              </v-list-item>
            </template>
          </v-select>
          <v-select
            v-model="stateRef"
            :disabled="gameRunning"
            class="my-1"
            hide-details
            rounded="0"
            variant="outlined"
            clearable
            label="State"
            :items="
              rom.user_states?.map((s) => ({
                title: s.file_name,
                subtitle: `${s.emulator} - ${formatBytes(s.file_size_bytes)}`,
                value: s,
              })) ?? []
            "
          >
            <template #selection="{ item }">
              <v-list-item class="pa-0" :title="item.value.file_name ?? ''">
                <template #append>
                  <v-chip size="x-small" class="ml-1" color="orange" label>{{
                    item.value.emulator
                  }}</v-chip>
                  <v-chip size="x-small" class="ml-1" label
                  >{{ formatBytes(item.value.file_size_bytes) }}
                </v-chip>
                <v-chip size="small" class="ml-1" label>
                  {{ formatTimestamp(item.value.updated_at) }}
                </v-chip>
                </template>
              </v-list-item>
            </template>
            <template #item="{ props, item }">
              <v-list-item
                class="py-4"
                v-bind="props"
                :title="item.value.file_name ?? ''"
              >
                <template #append>
                  <v-chip size="x-small" class="ml-1" color="orange" label>{{
                    item.value.emulator
                  }}</v-chip>
                  <v-chip size="x-small" class="ml-1" label
                  >{{ formatBytes(item.value.file_size_bytes) }}
                </v-chip>
                <v-chip size="small" class="ml-1" label>
                  {{ formatTimestamp(item.value.updated_at) }}
                </v-chip>
                </template>
              </v-list-item>
            </template>
          </v-select>
          <!-- <v-select
            class="my-1"
            hide-details
            variant="outlined"
            clearable
            rounded="0"
            disabled
            label="Patch"
            :items="[
              'Advance Wars Balance (AW1) by Kartal',
              'War Room Sturm (AW1) by Kartal',
            ]"
          /> -->
        </v-col>
      </v-row>
      <v-row class="px-3 py-3 text-center" no-gutters>
        <v-col>
          <v-divider class="my-4" />
          <v-row class="align-center" no-gutters>
            <v-col>
              <v-btn
                block
                size="large"
                rounded="0"
                @click="onFullScreenChange"
                :disabled="gameRunning"
                :variant="fullScreenOnPlay ? 'flat' : 'outlined'"
                :color="fullScreenOnPlay ? 'romm-accent-1' : ''"
                ><v-icon class="mr-1">{{
                  fullScreenOnPlay
                    ? "mdi-checkbox-outline"
                    : "mdi-checkbox-blank-outline"
                }}</v-icon
                >Full screen</v-btn
              >
            </v-col>
            <v-col
              cols="12"
              :sm="gameRunning ? 12 : 7"
              :xl="gameRunning ? 12 : 9"
            >
              <v-btn
                color="romm-accent-1"
                block
                :disabled="gameRunning"
                rounded="0"
                variant="outlined"
                size="large"
                prepend-icon="mdi-play"
                @click="onPlay()"
                >Play
              </v-btn>
            </v-col>
          </v-row>
          <v-btn
            class="mt-4"
            block
            rounded="0"
            variant="outlined"
            size="large"
            prepend-icon="mdi-refresh"
            @click="$router.go(0)"
            >Reset session
          </v-btn>
          <v-btn
            class="mt-4"
            block
            rounded="0"
            variant="outlined"
            size="large"
            prepend-icon="mdi-arrow-left"
            @click="
              $router.push({
                name: 'rom',
                params: { rom: rom?.id },
              })
            "
            >Back to game details
          </v-btn>
          <v-btn
            class="mt-4"
            block
            rounded="0"
            variant="outlined"
            size="large"
            prepend-icon="mdi-arrow-left"
            @click="
              $router.push({
                name: 'platform',
                params: { platform: rom?.platform_id },
              })
            "
            >Back to gallery
          </v-btn>
        </v-col>
      </v-row>
    </v-col>
  </v-row>
</template>

<style>
#game-wrapper {
  aspect-ratio: 16 / 9;
}
</style>
