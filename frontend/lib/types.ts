export type UserRole = "superadmin" | "table_admin" | "dealer" | "waiter";

export type User = {
  id: number;
  username: string;
  role: UserRole;
  table_id: number | null;
  is_active: boolean;
  hourly_rate: number | null;
};

export type Table = {
  id: number;
  name: string;
  seats_count: number;
};

export type Staff = {
  id: number;
  username: string;
  role: UserRole;
  hourly_rate: number | null;
};

export type SessionDealerAssignment = {
  id: number;
  dealer_id: number;
  dealer_username: string;
  dealer_hourly_rate: number | null;
  started_at: string;
  ended_at: string | null;
  rake: number | null;
};

export type Session = {
  id: string;
  table_id: number;
  date: string;
  status: string;
  created_at: string;
  closed_at: string | null;
  dealer_id: number | null;
  waiter_id: number | null;
  dealer: Staff | null;
  waiter: Staff | null;
  chips_in_play: number | null;
  dealer_assignments: SessionDealerAssignment[];
};

export type Seat = {
  seat_no: number;
  player_name: string | null;
  total: number;
  cash: number;
  credit: number;
};

export type ChipPurchase = {
  id: number;
  table_id: number;
  table_name: string;
  session_id: string | null;
  seat_no: number;
  amount: number;
  created_at: string;
  created_by_user_id: number | null;
  created_by_username: string | null;
  payment_type: "cash" | "credit";
};

export type CasinoBalanceAdjustment = {
  id: number;
  created_at: string;
  amount: number;
  comment: string;
  created_by_user_id: number;
  created_by_username: string;
};
