/- Original synthetic corpus for actual Expr extraction tests. -/
namespace LPAF.Fixture

def twice (n : Nat) : Nat := Nat.add n n
def twiceRenamed (k : Nat) : Nat := Nat.add k k

def leftStep (n : Nat) : Nat := twice n
def rightStep (n : Nat) : Nat := twice n
def diamond (n : Nat) : Nat := Nat.add (leftStep n) (rightStep n)

theorem trueSeed : True := True.intro
theorem trueCopy : True := trueSeed
theorem bothTrue : True ∧ True := And.intro trueSeed trueSeed

def literalNat : Nat := 1
def literalString : String := "1"

def identityPoly {α : Sort u} (x : α) : α := x

axiom declaredPremise : True

end LPAF.Fixture
