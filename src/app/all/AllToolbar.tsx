"use client";
import type { HomeFilters } from "../_components/home/home-routes";
import { FeedToolbar } from "../_components/feed/FeedToolbar";
export function AllToolbar({ filters }: { filters: HomeFilters }) { return <FeedToolbar filters={filters} base="/all" />; }
